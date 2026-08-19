"""Vistas operativas del shell interno (/pos/...) estilo POS."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.pos.views import cajero_required


@cajero_required
def hub_inicio(request):
    from decimal import Decimal
    from django.db.models import Sum
    from django.utils import timezone

    from apps.pedidos.models import Pedido
    from apps.pagos.models import Pago
    from apps.pos.models import CajaSesion
    from apps.tienda.models import ImportacionCatalogo, Producto

    import_activa = ImportacionCatalogo.objects.filter(
        estado__in=['pendiente', 'procesando']
    ).first()
    bloqueados = Producto.objects.filter(venta_bloqueada=True).count()

    # Caja del usuario actual (una sesión abierta por cajero)
    sesion = CajaSesion.objects.filter(
        cajero=request.user, estado=CajaSesion.ESTADO_ABIERTA
    ).first()

    caja_resumen = None
    if sesion:
        pagos = Pago.objects.filter(
            pedido__caja_sesion=sesion, estado=Pago.ESTADO_APROBADO
        )
        total_ventas = pagos.aggregate(t=Sum('monto'))['t'] or Decimal('0.00')
        total_efectivo = (
            pagos.filter(metodo=Pago.METODO_EFECTIVO).aggregate(t=Sum('monto'))['t']
            or Decimal('0.00')
        )
        caja_resumen = {
            'sesion': sesion,
            'total_ventas': total_ventas,
            'total_efectivo': total_efectivo,
            'ingresos_caja': (
                sesion.movimientos.filter(tipo='ingreso').aggregate(t=Sum('monto'))['t']
                or Decimal('0.00')
            ),
            'egresos_caja': (
                sesion.movimientos.filter(tipo='egreso').aggregate(t=Sum('monto'))['t']
                or Decimal('0.00')
            ),
            'esperado_caja': (
                sesion.monto_apertura + total_efectivo + sesion.total_movimientos_neto()
            ),
            'n_tickets': pagos.count(),
            'n_movimientos': sesion.movimientos.count(),
        }

    hoy = timezone.localdate()
    ventas_hoy = Pedido.objects.filter(
        canal=Pedido.CANAL_POS,
        fecha_pedido__date=hoy,
        atendido_por=request.user,
    ).count()

    context = {
        'ventas_hoy': ventas_hoy,
        'ventas_tienda_total': Pedido.objects.filter(canal=Pedido.CANAL_POS).count(),
        'pedidos_web_pendientes': Pedido.objects.filter(
            canal=Pedido.CANAL_WEB, estado=Pedido.ESTADO_PENDIENTE
        ).count(),
        'productos_total': Producto.objects.filter(activo=True).count(),
        'import_activa': import_activa,
        'bloqueados': bloqueados,
        'sesion_caja': sesion,
        'caja_resumen': caja_resumen,
        'es_superuser': request.user.is_superuser,
    }
    return render(request, 'pos/hub_inicio.html', context)


@cajero_required
def hub_ventas_tienda(request):
    from apps.pedidos.models import Pedido

    q = request.GET.get('q', '').strip()
    # Default tienda; canal vacío = todos (tienda + web)
    canal = request.GET.get('canal', Pedido.CANAL_POS)
    if canal is None:
        canal = Pedido.CANAL_POS
    canal = canal.strip()
    qs = Pedido.objects.select_related('cliente', 'atendido_por').order_by('-fecha_pedido')
    if canal in (Pedido.CANAL_POS, Pedido.CANAL_WEB):
        qs = qs.filter(canal=canal)
    if q:
        from apps.tienda.search import filtrar_por_tokens
        qs = filtrar_por_tokens(
            qs, q,
            [
                'numero_pedido',
                'cliente__nombre_completo',
                'cliente__dni_ruc',
                'cliente__telefono',
                'cliente__correo',
            ],
        )
    page = Paginator(qs, 25).get_page(request.GET.get('page'))
    titulos = {
        Pedido.CANAL_POS: ('Ventas de tienda', 'Ventas registradas en caja POS'),
        Pedido.CANAL_WEB: ('Pedidos web', 'Órdenes desde la tienda en línea'),
        '': ('Todos los pedidos', 'Tienda + web en una sola lista'),
    }
    titulo, subtitulo = titulos.get(canal, titulos[''])
    return render(request, 'pos/hub_lista.html', {
        'titulo': titulo,
        'subtitulo': subtitulo,
        'q': q,
        'canal': canal,
        'page_obj': page,
        'modo': 'pedidos',
        'search_placeholder': 'Nº pedido, DNI, teléfono o cliente…',
    })


@cajero_required
def hub_pedidos_web(request):
    """Atajo a la lista unificada filtrada a canal web."""
    from django.urls import reverse
    from apps.pedidos.models import Pedido
    return redirect(reverse('pos:hub_ventas') + f'?canal={Pedido.CANAL_WEB}')


@cajero_required
def hub_pedido_detalle(request, pedido_id):
    """Detalle de una venta / pedido (ítems, pagos, ticket, entrega)."""
    from apps.pedidos.models import Pedido
    from apps.pagos.models import Pago
    from apps.pedidos.services import confirmar_pago_pedido, anular_pedido, StockInsuficienteError
    from apps.mantenimiento.models import EquipoRegistrado
    from apps.tienda.models import Producto
    from django.utils import timezone
    import datetime

    pedido = get_object_or_404(
        Pedido.objects.select_related(
            'cliente', 'atendido_por', 'caja_sesion', 'sede', 'ticket_pos',
        ).prefetch_related('detalles__producto', 'pagos', 'equipos_registrados'),
        pk=pedido_id,
    )

    if request.method == 'POST':
        accion = request.POST.get('accion')
        canal_q = request.GET.get('canal', pedido.canal)

        if accion == 'subir_voucher':
            if pedido.canal == Pedido.CANAL_POS:
                messages.info(request, 'En venta POS no se requiere voucher.')
            else:
                pago = get_object_or_404(Pago, pk=request.POST.get('pago_id'), pedido=pedido)
                archivo = request.FILES.get('voucher')
                if not archivo:
                    messages.error(request, 'Selecciona una imagen del voucher.')
                else:
                    try:
                        from apps.tienda.images import convertir_a_webp
                        webp = convertir_a_webp(archivo)
                        pago.voucher.save(webp.name, webp, save=True)
                        if not pedido.voucher:
                            pedido.voucher.save(webp.name, webp, save=True)
                    except Exception:
                        pago.voucher = archivo
                        pago.save(update_fields=['voucher'])
                    messages.success(request, 'Voucher guardado (WebP).')

        elif accion == 'confirmar_pago':
            pago = pedido.pagos.filter(estado=Pago.ESTADO_PENDIENTE).order_by('id').first()
            if not pago:
                messages.error(request, 'No hay pago pendiente para confirmar.')
            elif pedido.estado != Pedido.ESTADO_PENDIENTE:
                messages.error(request, 'Este pedido ya no está pendiente de pago.')
            else:
                try:
                    confirmar_pago_pedido(
                        pedido,
                        metodo=pago.metodo,
                        pago=pago,
                        usuario=request.user,
                    )
                    if not pedido.atendido_por_id:
                        pedido.atendido_por = request.user
                        pedido.save(update_fields=['atendido_por'])
                    messages.success(
                        request,
                        'Pago confirmado. Stock actualizado y equipos registrados.',
                    )
                except StockInsuficienteError as e:
                    messages.error(request, e.mensaje)
                except Exception as e:
                    messages.error(request, f'No se pudo confirmar el pago: {e}')

        elif accion == 'listo_recojo':
            if pedido.canal == Pedido.CANAL_POS:
                messages.info(request, 'En venta POS el pedido ya queda entregado al cobrar.')
            elif pedido.estado != Pedido.ESTADO_PAGADO:
                messages.error(request, 'Solo pedidos pagados pueden marcarse listos para recojo.')
            else:
                pedido.estado = Pedido.ESTADO_ENVIADO
                pedido.save(update_fields=['estado'])
                messages.success(request, 'Pedido marcado como listo para recojo.')

        elif accion == 'confirmar_entrega':
            if pedido.canal == Pedido.CANAL_POS:
                messages.info(request, 'En venta POS el pedido ya queda entregado al cobrar.')
            elif pedido.estado not in (Pedido.ESTADO_PAGADO, Pedido.ESTADO_ENVIADO):
                messages.error(request, 'Confirma el pago antes de entregar.')
            else:
                pedido.estado = Pedido.ESTADO_ENTREGADO
                update_fields = ['estado']
                if not pedido.atendido_por_id:
                    pedido.atendido_por = request.user
                    update_fields.append('atendido_por')
                pedido.save(update_fields=update_fields)
                messages.success(request, 'Entrega confirmada. Pedido cerrado.')

        elif accion == 'guardar_serie':
            equipo_id = request.POST.get('equipo_id')
            serie = (request.POST.get('numero_serie') or '').strip().upper()
            if not serie:
                messages.error(request, 'Ingresa el código único / número de serie.')
            else:
                equipo = get_object_or_404(EquipoRegistrado, pk=equipo_id, pedido_origin=pedido)
                if (
                    EquipoRegistrado.objects.filter(numero_serie=serie)
                    .exclude(pk=equipo.pk)
                    .exists()
                ):
                    messages.error(request, f'La serie {serie} ya está registrada.')
                else:
                    equipo.numero_serie = serie
                    equipo.save(update_fields=['numero_serie'])
                    messages.success(request, f'Serie actualizada: {serie}')

        elif accion == 'agregar_serie':
            detalle_id = request.POST.get('detalle_id')
            serie = (request.POST.get('numero_serie') or '').strip().upper()
            detalle = get_object_or_404(pedido.detalles.select_related('producto'), pk=detalle_id)
            prod = detalle.producto
            es_eq = prod.tipo == Producto.TIPO_HERRAMIENTA or prod.familia_sap == 'EQUIPOS'
            if not es_eq:
                messages.error(request, 'Este producto no requiere registro de serie.')
            elif not serie:
                messages.error(request, 'Ingresa el código único / número de serie.')
            elif EquipoRegistrado.objects.filter(numero_serie=serie).exists():
                messages.error(request, f'La serie {serie} ya está registrada.')
            else:
                registrados = EquipoRegistrado.objects.filter(
                    pedido_origin=pedido, producto=prod,
                ).count()
                if registrados >= detalle.cantidad:
                    messages.error(request, 'Ya se registraron todas las series de este ítem.')
                else:
                    hoy = timezone.now().date()
                    EquipoRegistrado.objects.create(
                        cliente=pedido.cliente,
                        pedido_origin=pedido,
                        producto=prod,
                        numero_serie=serie,
                        fecha_compra=hoy,
                        garantia_hasta=hoy + datetime.timedelta(days=365),
                        estado=EquipoRegistrado.ESTADO_ACTIVO,
                    )
                    messages.success(request, f'Serie {serie} registrada.')

        elif accion == 'anular_venta':
            if not pedido.puede_anular:
                messages.error(request, 'Esta venta ya está anulada.')
            else:
                motivo = (request.POST.get('motivo') or '').strip()
                anular_pedido(pedido, usuario=request.user, motivo=motivo)
                messages.success(
                    request,
                    f'{pedido.numero_pedido} anulada. '
                    'El documento se conserva; el stock se devolvió si correspondía '
                    'y ya no suma en caja.',
                )

        return redirect(f"{reverse('pos:hub_pedido_detalle', args=[pedido.id])}?canal={canal_q}")

    ticket = getattr(pedido, 'ticket_pos', None)
    detalles = list(pedido.detalles.select_related('producto').all())
    equipos = list(pedido.equipos_registrados.select_related('producto').order_by('id'))
    pago_pendiente = pedido.pagos.filter(estado=Pago.ESTADO_PENDIENTE).exists()

    # Una fila de serie por unidad (si compró 2 del mismo modelo → 2 códigos únicos)
    from collections import defaultdict
    eqs_por_prod = defaultdict(list)
    for eq in equipos:
        eqs_por_prod[eq.producto_id].append(eq)
    series_grupos = []
    for det in detalles:
        prod = det.producto
        es_eq = prod.tipo == Producto.TIPO_HERRAMIENTA or prod.familia_sap == 'EQUIPOS'
        if not es_eq:
            continue
        eqs = eqs_por_prod.get(prod.id, [])
        unidades = []
        for i in range(det.cantidad):
            unidades.append({
                'indice': i + 1,
                'total': det.cantidad,
                'equipo': eqs[i] if i < len(eqs) else None,
            })
        series_grupos.append({
            'detalle': det,
            'producto': prod,
            'unidades': unidades,
            'faltantes': max(0, det.cantidad - len(eqs)),
            'puede_agregar': len(eqs) < det.cantidad,
        })

    return render(request, 'pos/hub_pedido_detalle.html', {
        'pedido': pedido,
        'detalles': detalles,
        'pagos': pedido.pagos.all().order_by('id'),
        'ticket': ticket,
        'equipos': equipos,
        'series_grupos': series_grupos,
        'pago_pendiente': pago_pendiente,
        'volver_canal': request.GET.get('canal', pedido.canal),
    })


@cajero_required
def hub_productos(request):
    from apps.tienda.models import Producto
    from apps.tienda.search import filtrar_productos

    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '').strip()
    solo_bloqueados = request.GET.get('bloqueados') == '1'
    qs = Producto.objects.select_related('categoria').order_by('-fecha_creacion')
    if q:
        qs = filtrar_productos(qs, q)
    if tipo in ('herramienta', 'accesorio', 'repuesto'):
        qs = qs.filter(tipo=tipo)
    if solo_bloqueados:
        qs = qs.filter(venta_bloqueada=True)
    page = Paginator(qs, 40).get_page(request.GET.get('page'))
    return render(request, 'pos/hub_lista.html', {
        'titulo': 'Productos',
        'subtitulo': 'Catálogo interno · busca por código o nombre',
        'q': q,
        'tipo': tipo,
        'solo_bloqueados': solo_bloqueados,
        'page_obj': page,
        'modo': 'productos',
        'search_placeholder': 'Código, nombre o modelo…',
    })


@cajero_required
def hub_clientes(request):
    from apps.clientes.models import Cliente
    from apps.tienda.search import filtrar_por_tokens

    q = request.GET.get('q', '').strip()
    qs = Cliente.objects.all().order_by('-fecha_registro')
    if q:
        qs = filtrar_por_tokens(qs, q, ['nombre_completo', 'dni_ruc', 'telefono', 'correo'])
    page = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request, 'pos/hub_lista.html', {
        'titulo': 'Clientes',
        'subtitulo': 'CRM de tienda y web',
        'q': q,
        'page_obj': page,
        'modo': 'clientes',
        'search_placeholder': 'Nombre, DNI/RUC o teléfono…',
    })


@cajero_required
def hub_pagos(request):
    from apps.pagos.models import Pago

    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '').strip()
    qs = Pago.objects.select_related('pedido', 'pedido__cliente').order_by('-fecha_pago')
    if q:
        from apps.tienda.search import filtrar_por_tokens
        qs = filtrar_por_tokens(
            qs, q,
            ['pedido__numero_pedido', 'pedido__cliente__nombre_completo', 'referencia_externa'],
        )
    if estado:
        qs = qs.filter(estado=estado)
    page = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request, 'pos/hub_lista.html', {
        'titulo': 'Pagos',
        'subtitulo': 'Confirmaciones y métodos de pago',
        'q': q,
        'estado': estado,
        'page_obj': page,
        'modo': 'pagos',
        'search_placeholder': 'Pedido, cliente o referencia…',
    })


@cajero_required
def hub_movimientos(request):
    from apps.inventario.models import MovimientoInventario

    q = request.GET.get('q', '').strip()
    tipo_f = (request.GET.get('tipo') or '').strip()
    qs = (
        MovimientoInventario.objects.select_related('producto', 'usuario')
        .order_by('-fecha')
    )
    if tipo_f in (
        MovimientoInventario.TIPO_ENTRADA,
        MovimientoInventario.TIPO_SALIDA,
    ):
        qs = qs.filter(tipo=tipo_f)
    if q:
        from apps.tienda.search import filtrar_por_tokens
        qs = filtrar_por_tokens(
            qs, q,
            ['producto__nombre', 'producto__codigo_articulo'],
        )
    page = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request, 'pos/hub_lista.html', {
        'titulo': 'Movimientos de stock',
        'subtitulo': 'Entradas (ingresos) y salidas de inventario · busca por código para ver el historial de un producto',
        'q': q,
        'tipo': tipo_f,
        'page_obj': page,
        'modo': 'movimientos',
        'search_placeholder': 'Producto o código…',
    })


@cajero_required
def hub_productos_web(request):
    """Solo productos ya publicados en web. Agregar vía popup de búsqueda."""
    from apps.tienda.models import Producto

    q = request.GET.get('q', '').strip()
    qs = (
        Producto.objects.filter(activo=True, mostrar_en_web=True)
        .exclude(tipo=Producto.TIPO_REPUESTO)
        .select_related('categoria')
        .order_by('nombre')
    )
    if q:
        from apps.tienda.search import filtrar_productos
        qs = filtrar_productos(qs, q)
    page = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request, 'pos/hub_productos_web.html', {
        'page_obj': page,
        'q': q,
        'en_web': qs.count() if not q else Producto.objects.filter(mostrar_en_web=True).count(),
    })


@cajero_required
def hub_productos_web_buscar(request):
    """AJAX: buscar en catálogo interno para agregar a web."""
    from apps.tienda.models import Producto

    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'productos': [], 'hint': 'Escribe al menos 2 caracteres'})

    qs = (
        Producto.objects.filter(activo=True, mostrar_en_web=False)
        .exclude(tipo=Producto.TIPO_REPUESTO)
        .order_by('nombre')
    )
    from apps.tienda.search import filtrar_productos
    qs = filtrar_productos(qs, q)[:25]
    data = [{
        'id': p.id,
        'codigo': p.codigo_articulo,
        'nombre': p.nombre,
        'precio_venta': str(p.precio_venta),
        'precio_lista': str(p.precio_venta),
        'precio_con_igv': str(p.precio_lista_con_igv),
        'stock': p.stock,
        'stock_web': p.stock_web,
        'tipo': p.get_tipo_display(),
    } for p in qs]
    return JsonResponse({'productos': data})


@cajero_required
@require_http_methods(['POST'])
def hub_producto_web_toggle(request, producto_id):
    """Publicar / editar / ocultar producto en web (con precios promo y stock)."""
    from decimal import Decimal, InvalidOperation
    from apps.sistema.activity import registrar_actividad
    from apps.tienda.models import Producto

    producto = get_object_or_404(Producto, pk=producto_id)
    accion = request.POST.get('accion', 'publicar')

    if accion == 'ocultar':
        producto.mostrar_en_web = False
        producto.save(update_fields=['mostrar_en_web'])
        registrar_actividad(
            request, tipo='productos_web', accion='Quitar de web',
            detalle=f'{producto.codigo_articulo} · {producto.nombre}',
        )
        payload = {
            'ok': True,
            'id': producto.id,
            'mostrar_en_web': False,
            'mensaje': f'«{producto.codigo_articulo}» quitado de la web.',
        }
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse(payload)
        messages.success(request, payload['mensaje'])
        return redirect(request.POST.get('next') or 'pos:hub_productos_web')

    def _dec(key):
        raw = (request.POST.get(key) or '').strip().replace(',', '')
        if not raw:
            return None
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            return None

    def _int(key, default=0):
        raw = (request.POST.get(key) or '').strip()
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return default

    precio_tachado = _dec('precio_tachado')
    precio_web = _dec('precio_web')
    if precio_web is None:
        precio_web = producto.precio_lista_con_igv

    stock_tienda = _int('stock_tienda', producto.stock)
    stock_web = _int('stock_web', producto.stock_web)

    if precio_tachado is not None and precio_web is not None and precio_tachado <= precio_web:
        err = 'El precio tachado debe ser mayor al precio final para marcar promoción.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': err}, status=400)
        messages.error(request, err)
        return redirect('pos:hub_productos_web')

    producto.precio_tachado = precio_tachado
    producto.precio_web = precio_web
    producto.stock = stock_tienda
    producto.stock_web = stock_web
    producto.mostrar_en_web = True
    producto.save(update_fields=[
        'precio_tachado', 'precio_web', 'stock', 'stock_web', 'mostrar_en_web',
    ])

    promo = ' · promoción' if producto.en_promocion else ''
    registrar_actividad(
        request, tipo='productos_web', accion='Publicar / editar web',
        detalle=(
            f'{producto.codigo_articulo} · final S/ {producto.precio_publico} · '
            f'tienda {producto.stock} / web {producto.stock_web}{promo}'
        ),
    )
    payload = {
        'ok': True,
        'id': producto.id,
        'mostrar_en_web': True,
        'en_promocion': producto.en_promocion,
        'precio_tachado': str(producto.precio_tachado) if producto.precio_tachado is not None else '',
        'precio_web': str(producto.precio_web) if producto.precio_web is not None else '',
        'precio_publico': str(producto.precio_publico),
        'stock': producto.stock,
        'stock_web': producto.stock_web,
        'mensaje': (
            f'«{producto.codigo_articulo}» en web '
            f'(tienda: {producto.stock}, web: {producto.stock_web}){promo}.'
        ),
    }
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(payload)
    messages.success(request, payload['mensaje'])
    return redirect(request.POST.get('next') or 'pos:hub_productos_web')


@cajero_required
@require_http_methods(['POST'])
def hub_productos_web_bulk(request):
    from apps.sistema.activity import registrar_actividad
    from apps.tienda.models import Producto

    ids = request.POST.getlist('ids')
    accion = request.POST.get('accion')
    if ids and accion == 'ocultar':
        n = Producto.objects.filter(id__in=ids).update(mostrar_en_web=False)
        registrar_actividad(
            request, tipo='productos_web', accion='Ocultar varios de web',
            detalle=f'{n} producto(s)',
        )
        messages.success(request, f'{n} producto(s) ocultados de la web.')
    return redirect('pos:hub_productos_web')


@cajero_required
def hub_producto_editar(request, producto_id):
    """Editar producto (datos, precios, ficha técnica, galería WebP, stock)."""
    from decimal import Decimal, InvalidOperation

    from apps.sistema.activity import registrar_actividad
    from apps.tienda.images import convertir_a_webp
    from apps.tienda.models import Categoria, Producto, ProductoAtributo, ProductoImagen
    from apps.tienda.precios import sin_igv

    producto = get_object_or_404(Producto, pk=producto_id)
    volver = request.GET.get('next') or request.POST.get('next') or ''

    def _dec(key):
        raw = (request.POST.get(key) or '').strip().replace(',', '')
        if not raw:
            return None
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            return None

    def _int(key, default=0):
        try:
            return max(0, int(request.POST.get(key) or default))
        except (TypeError, ValueError):
            return default

    if request.method == 'POST':
        accion = request.POST.get('accion', 'guardar')

        if accion == 'eliminar_imagen':
            img_id = request.POST.get('imagen_id')
            ProductoImagen.objects.filter(pk=img_id, producto=producto).delete()
            messages.success(request, 'Imagen eliminada.')
            return redirect('pos:hub_producto_editar', producto_id=producto.id)

        if accion == 'set_principal':
            img = ProductoImagen.objects.filter(
                pk=request.POST.get('imagen_id'), producto=producto
            ).first()
            if img and img.imagen:
                ProductoImagen.objects.filter(producto=producto).update(es_principal=False)
                img.es_principal = True
                img.save(update_fields=['es_principal'])
                producto.imagen_principal = img.imagen
                producto.save(update_fields=['imagen_principal'])
                messages.success(request, 'Imagen marcada como principal.')
            return redirect('pos:hub_producto_editar', producto_id=producto.id)

        codigo = (request.POST.get('codigo_articulo') or '').strip().upper()[:50]
        nombre = (request.POST.get('nombre') or '').strip()[:255]
        if not codigo or not nombre:
            messages.error(request, 'El código y el nombre son obligatorios.')
            return redirect('pos:hub_producto_editar', producto_id=producto.id)
        if codigo != producto.codigo_articulo and Producto.objects.filter(
            codigo_articulo=codigo
        ).exclude(pk=producto.pk).exists():
            messages.error(request, f'El código «{codigo}» ya existe en otro producto.')
            return redirect('pos:hub_producto_editar', producto_id=producto.id)

        producto.codigo_articulo = codigo
        producto.nombre = nombre
        producto.nombre_web = (request.POST.get('nombre_web') or '').strip()[:255]
        producto.descripcion = (request.POST.get('descripcion') or '').strip() or None
        producto.mostrar_ficha_tecnica = request.POST.get('mostrar_ficha_tecnica') == '1'
        producto.mostrar_en_web = request.POST.get('mostrar_en_web') == '1'
        producto.activo = request.POST.get('activo') == '1'

        tipo = request.POST.get('tipo', '')
        if tipo in dict(Producto.TIPO_CHOICES):
            producto.tipo = tipo

        cat_id = (request.POST.get('categoria_id') or '').strip()
        producto.categoria = Categoria.objects.filter(pk=cat_id).first() if cat_id else None

        precio_venta = _dec('precio_venta')
        precio_con_igv = _dec('precio_con_igv')
        if precio_venta is not None:
            producto.precio_venta = max(Decimal('0'), precio_venta)
        elif precio_con_igv is not None:
            producto.precio_venta = max(Decimal('0'), sin_igv(precio_con_igv))

        precio_costo = _dec('precio_costo')
        if precio_costo is not None:
            producto.precio_costo = max(Decimal('0'), precio_costo)

        precio_web = _dec('precio_web')
        precio_tachado = _dec('precio_tachado')
        if precio_web is not None:
            producto.precio_web = precio_web
        if 'precio_tachado' in request.POST:
            producto.precio_tachado = precio_tachado
        producto.stock = _int('stock', producto.stock)
        producto.stock_web = _int('stock_web', producto.stock_web)

        if (
            producto.precio_tachado is not None
            and producto.precio_web is not None
            and producto.precio_tachado <= producto.precio_web
        ):
            messages.error(
                request,
                'El precio tachado debe ser mayor al precio final para marcar promoción.',
            )
            return redirect('pos:hub_producto_editar', producto_id=producto.id)

        producto.save()

        # Ficha técnica: reemplazar filas no vacías
        nombres = request.POST.getlist('attr_nombre')
        valores = request.POST.getlist('attr_valor')
        ProductoAtributo.objects.filter(producto=producto).delete()
        orden = 0
        for nom, val in zip(nombres, valores):
            nom = (nom or '').strip()[:120]
            val = (val or '').strip()[:255]
            if not nom and not val:
                continue
            if not nom or not val:
                continue
            ProductoAtributo.objects.create(
                producto=producto, nombre=nom, valor=val, orden=orden,
            )
            orden += 1

        # Nuevas imágenes → WebP
        for f in request.FILES.getlist('imagenes'):
            webp = convertir_a_webp(f)
            img = ProductoImagen(producto=producto, orden=producto.imagenes.count())
            img.imagen.save(webp.name, webp, save=True)
            if not producto.imagen_principal:
                producto.imagen_principal.save(webp.name, webp, save=True)
                img.es_principal = True
                img.save(update_fields=['es_principal'])

        registrar_actividad(
            request, tipo='productos_web', accion='Editar producto',
            detalle=(
                f'{producto.codigo_articulo} · {producto.nombre_publico} · '
                f'Lista S/ {producto.precio_venta}'
            ),
        )
        messages.success(request, f'Producto «{producto.codigo_articulo}» actualizado.')
        if volver:
            return redirect(volver)
        if producto.mostrar_en_web:
            return redirect('pos:hub_productos_web')
        return redirect('pos:hub_productos')

    atributos = list(producto.atributos.all())
    # Al menos 3 filas vacías para agregar
    while len(atributos) < 3:
        atributos.append(None)

    return render(request, 'pos/hub_producto_editar.html', {
        'producto': producto,
        'atributos': atributos,
        'imagenes': producto.imagenes.all(),
        'next': volver,
        'tipos': Producto.TIPO_CHOICES,
        'categorias': Categoria.objects.all().order_by('nombre'),
    })


@cajero_required
def hub_producto_nuevo(request):
    """Crear un nuevo producto o servicio/concepto manual para el negocio."""
    from decimal import Decimal, InvalidOperation
    from apps.sistema.activity import registrar_actividad
    from apps.tienda.models import Categoria, Producto

    if request.method == 'POST':
        codigo = (request.POST.get('codigo_articulo') or '').strip().upper()[:50]
        nombre = (request.POST.get('nombre') or '').strip().upper()[:255]
        tipo = request.POST.get('tipo', Producto.TIPO_SERVICIO)
        precio_str = (request.POST.get('precio_venta') or '').strip().replace(',', '')
        categoria_id = request.POST.get('categoria_id')

        if not codigo:
            import uuid
            prefix_code = 'SRV' if tipo == Producto.TIPO_SERVICIO else 'PRD'
            codigo = f"{prefix_code}-{uuid.uuid4().hex[:6].upper()}"

        if not nombre:
            messages.error(request, 'Debes ingresar una descripción o nombre.')
            return render(request, 'pos/hub_producto_nuevo.html', {
                'tipos': Producto.TIPO_CHOICES,
                'categorias': Categoria.objects.all().order_by('nombre'),
                'tipo_seleccionado': tipo,
            })

        if Producto.objects.filter(codigo_articulo=codigo).exists():
            messages.error(request, f'El código/SKU «{codigo}» ya existe. Ingresa uno diferente.')
            return render(request, 'pos/hub_producto_nuevo.html', {
                'tipos': Producto.TIPO_CHOICES,
                'categorias': Categoria.objects.all().order_by('nombre'),
                'tipo_seleccionado': tipo,
            })

        try:
            precio = Decimal(precio_str) if precio_str else Decimal('0.00')
        except (InvalidOperation, ValueError):
            precio = Decimal('0.00')

        categoria = Categoria.objects.filter(pk=categoria_id).first() if categoria_id else None

        prod = Producto.objects.create(
            codigo_articulo=codigo,
            nombre=nombre,
            tipo=tipo,
            precio_venta=precio,
            categoria=categoria,
            activo=True,
            stock=0 if tipo == Producto.TIPO_SERVICIO else int(request.POST.get('stock', 0) or 0),
        )

        registrar_actividad(
            request,
            tipo='productos',
            accion='Crear producto/servicio',
            detalle=f'[{prod.get_tipo_display()}] {prod.codigo_articulo} - {prod.nombre} (S/ {precio})',
        )

        messages.success(request, f'{prod.get_tipo_display()} «{prod.nombre}» creado con éxito.')
        return redirect('pos:hub_productos')

    return render(request, 'pos/hub_producto_nuevo.html', {
        'tipos': Producto.TIPO_CHOICES,
        'categorias': Categoria.objects.all().order_by('nombre'),
        'tipo_seleccionado': request.GET.get('tipo', Producto.TIPO_SERVICIO),
    })



@cajero_required
def hub_inventario(request):
    """Ingreso / retiro de stock en bloque (tienda o web)."""
    from apps.inventario.models import MovimientoInventario

    q = (request.GET.get('q') or '').strip()
    tipo_f = (request.GET.get('tipo') or '').strip()
    qs = (
        MovimientoInventario.objects.select_related('producto', 'usuario')
        .order_by('-fecha')
    )
    if tipo_f in (
        MovimientoInventario.TIPO_ENTRADA,
        MovimientoInventario.TIPO_SALIDA,
    ):
        qs = qs.filter(tipo=tipo_f)
    if q:
        from apps.tienda.search import filtrar_por_tokens
        qs = filtrar_por_tokens(
            qs, q,
            ['producto__nombre', 'producto__codigo_articulo'],
        )
    recientes = qs[:80]
    return render(request, 'pos/hub_inventario.html', {
        'recientes': recientes,
        'q': q,
        'tipo_filtro': tipo_f,
        'motivos_entrada': [
            (MovimientoInventario.MOTIVO_COMPRA, 'Compra / mercadería nueva'),
            (MovimientoInventario.MOTIVO_AJUSTE, 'Ajuste de inventario'),
        ],
        'motivos_salida': [
            (MovimientoInventario.MOTIVO_AJUSTE, 'Ajuste / corrección'),
            (MovimientoInventario.MOTIVO_MANTENIMIENTO, 'Desuso / taller'),
        ],
    })


@cajero_required
def hub_inventario_buscar(request):
    from apps.tienda.models import Producto

    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'productos': []})
    from apps.tienda.search import filtrar_productos
    qs = filtrar_productos(
        Producto.objects.filter(activo=True),
        q,
    ).order_by('nombre')[:30]
    return JsonResponse({'productos': [{
        'id': p.id,
        'codigo': p.codigo_articulo,
        'nombre': p.nombre,
        'stock': p.stock,
        'stock_web': p.stock_web,
    } for p in qs]})


@cajero_required
@require_http_methods(['POST'])
def hub_inventario_aplicar(request):
    """Aplica líneas JSON.

    tipos:
      - entrada / salida + destino tienda|web (ingreso o retiro)
      - transferencia + direccion tienda_a_web|web_a_tienda
    """
    import json
    from django.db import transaction
    from apps.inventario.models import MovimientoInventario
    from apps.sistema.activity import registrar_actividad
    from apps.tienda.models import Producto

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    tipo = payload.get('tipo')  # entrada | salida | transferencia
    motivo = payload.get('motivo') or MovimientoInventario.MOTIVO_AJUSTE
    destino = payload.get('destino', 'tienda')  # tienda | web
    direccion = payload.get('direccion', 'tienda_a_web')  # solo transferencia
    lineas = payload.get('lineas') or []

    if tipo not in ('entrada', 'salida', 'transferencia'):
        return JsonResponse({'ok': False, 'error': 'Tipo inválido'}, status=400)
    if not lineas:
        return JsonResponse({'ok': False, 'error': 'Agrega al menos un producto'}, status=400)
    if tipo == 'transferencia' and direccion not in ('tienda_a_web', 'web_a_tienda'):
        return JsonResponse({'ok': False, 'error': 'Dirección de transferencia inválida'}, status=400)

    aplicadas = 0
    errores = []

    with transaction.atomic():
        for linea in lineas:
            try:
                pid = int(linea.get('id'))
                cant = int(linea.get('cantidad', 0))
            except (TypeError, ValueError):
                continue
            if cant <= 0:
                continue
            producto = (
                Producto.objects.select_for_update()
                .filter(pk=pid)
                .first()
            )
            if not producto:
                errores.append(f'ID {pid} no existe')
                continue

            if tipo == 'transferencia':
                if direccion == 'tienda_a_web':
                    origen_stock = producto.stock
                    origen_label = 'tienda'
                    origen_destino = MovimientoInventario.DESTINO_TIENDA
                    destino_mov = MovimientoInventario.DESTINO_WEB
                else:
                    origen_stock = producto.stock_web
                    origen_label = 'web'
                    origen_destino = MovimientoInventario.DESTINO_WEB
                    destino_mov = MovimientoInventario.DESTINO_TIENDA

                if cant > origen_stock:
                    errores.append(
                        f'{producto.codigo_articulo}: solo hay {origen_stock} en {origen_label}'
                    )
                    continue

                MovimientoInventario.objects.create(
                    producto=producto,
                    tipo=MovimientoInventario.TIPO_SALIDA,
                    cantidad=cant,
                    motivo=MovimientoInventario.MOTIVO_TRANSFERENCIA,
                    destino=origen_destino,
                    usuario=request.user,
                )
                # Refetch after first movement updated stock via save()
                producto.refresh_from_db()
                MovimientoInventario.objects.create(
                    producto=producto,
                    tipo=MovimientoInventario.TIPO_ENTRADA,
                    cantidad=cant,
                    motivo=MovimientoInventario.MOTIVO_TRANSFERENCIA,
                    destino=destino_mov,
                    usuario=request.user,
                )
                aplicadas += 1
                continue

            if tipo == 'salida':
                disponible = producto.stock_web if destino == 'web' else producto.stock
                if cant > disponible:
                    errores.append(
                        f'{producto.codigo_articulo}: solo hay {disponible} en {destino}'
                    )
                    continue

            MovimientoInventario.objects.create(
                producto=producto,
                tipo=(
                    MovimientoInventario.TIPO_ENTRADA
                    if tipo == 'entrada'
                    else MovimientoInventario.TIPO_SALIDA
                ),
                cantidad=cant,
                motivo=motivo,
                destino=(
                    MovimientoInventario.DESTINO_WEB
                    if destino == 'web'
                    else MovimientoInventario.DESTINO_TIENDA
                ),
                usuario=request.user,
            )
            aplicadas += 1

    if tipo == 'transferencia':
        accion = f'Transferencia {direccion.replace("_", " ")}'
        mensaje = f'Se transfirieron {aplicadas} producto(s).'
    else:
        accion = f'Inventario {tipo} ({destino})'
        mensaje = f'Se aplicaron {aplicadas} movimiento(s).'

    registrar_actividad(
        request,
        tipo='inventario',
        accion=accion,
        detalle=f'{aplicadas} línea(s) · motivo {motivo}' + (
            f' · errores: {"; ".join(errores)}' if errores else ''
        ),
    )
    ok = aplicadas > 0
    if not ok and errores:
        mensaje = errores[0] if len(errores) == 1 else f'No se aplicó ningún movimiento. {"; ".join(errores)}'
    return JsonResponse({
        'ok': ok,
        'aplicadas': aplicadas,
        'errores': errores,
        'mensaje': mensaje,
    })


@cajero_required
def hub_actividad(request):
    from apps.sistema.models import LogActividad

    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '').strip()
    qs = LogActividad.objects.select_related('usuario').all()
    if q:
        from apps.tienda.search import filtrar_por_tokens
        qs = filtrar_por_tokens(
            qs, q,
            ['accion', 'detalle', 'usuario__username', 'ruta'],
        )
    if tipo:
        qs = qs.filter(tipo=tipo)
    page = Paginator(qs, 50).get_page(request.GET.get('page'))
    return render(request, 'pos/hub_actividad.html', {
        'page_obj': page,
        'q': q,
        'tipo': tipo,
        'tipos': LogActividad.TIPO_CHOICES,
    })


@cajero_required
def hub_importar(request):
    from django.utils import timezone
    from datetime import timedelta

    from apps.tienda.importers.makita_excel import limpiar_excels_importaciones_exitosas
    from apps.tienda.models import ImportacionCatalogo, Producto

    # Borrar Excel de importaciones ya exitosas (libera disco)
    try:
        limpiar_excels_importaciones_exitosas()
    except Exception:
        pass

    # Limpiar colgadas: pendientes > 10 min sin progreso
    stale = ImportacionCatalogo.objects.filter(estado__in=['pendiente', 'procesando'])
    for imp in stale:
        vieja = imp.fecha and (timezone.now() - imp.fecha) > timedelta(minutes=10)
        sin_avance = imp.total_procesadas == 0 and vieja
        # Si está procesando y aún tiene archivo, no marcar error solo por "sin archivo"
        # (puede haberse borrado tras éxito en carrera rara).
        if sin_avance:
            ImportacionCatalogo.objects.filter(pk=imp.pk).update(
                estado=ImportacionCatalogo.ESTADO_ERROR,
                mensaje_error=(
                    'Importación interrumpida (proceso detenido). '
                    'Vuelve a subir el Excel si necesitas reintentar.'
                ),
                fecha_fin=timezone.now(),
            )

    recientes = ImportacionCatalogo.objects.all()[:15]
    activa = ImportacionCatalogo.objects.filter(
        estado__in=['pendiente', 'procesando']
    ).first()
    bloqueados = Producto.objects.filter(venta_bloqueada=True).count()
    return render(request, 'pos/hub_importar.html', {
        'recientes': recientes,
        'activa': activa,
        'bloqueados': bloqueados,
    })


@cajero_required
@require_http_methods(['POST'])
def hub_importar_upload(request):
    from apps.tienda.importers.makita_excel import importar_catalogo_makita
    from apps.tienda.models import ImportacionCatalogo

    archivo = request.FILES.get('archivo')
    tipo = request.POST.get('tipo_archivo') or ImportacionCatalogo.TIPO_AUTO

    if not archivo:
        messages.error(request, 'Selecciona un archivo Excel (.xlsx).')
        return redirect('pos:hub_importar')
    if not archivo.name.lower().endswith(('.xlsx', '.xlsm')):
        messages.error(request, 'El archivo debe ser .xlsx (formato Makita).')
        return redirect('pos:hub_importar')

    # Evitar dos importaciones pesadas a la vez
    if ImportacionCatalogo.objects.filter(estado__in=['pendiente', 'procesando']).exists():
        messages.error(
            request,
            'Ya hay una importación en curso. Espera a que termine o cancélala.',
        )
        return redirect('pos:hub_importar')

    try:
        imp = importar_catalogo_makita(
            file_obj=archivo,
            archivo_nombre=archivo.name,
            tipo_archivo=tipo,
            usuario=request.user,
            en_background=True,
        )
        from apps.sistema.activity import registrar_actividad
        registrar_actividad(
            request, tipo='importacion', accion='Iniciar importación Excel',
            detalle=f'#{imp.id} · {archivo.name}',
        )
        messages.success(
            request,
            (
                f'Importación iniciada en segundo plano (#{imp.id}). '
                'Puedes seguir vendiendo; los productos del Excel quedan bloqueados '
                'hasta que se procese cada fila.'
            ),
        )
    except Exception as exc:
        messages.error(request, f'No se pudo iniciar la importación: {exc}')

    return redirect('pos:hub_importar')


@cajero_required
def hub_importar_estado(request, importacion_id):
    from apps.tienda.models import ImportacionCatalogo, Producto

    imp = get_object_or_404(ImportacionCatalogo, pk=importacion_id)
    return JsonResponse({
        'id': imp.id,
        'estado': imp.estado,
        'estado_display': imp.get_estado_display(),
        'progreso_pct': imp.progreso_pct,
        'total_filas': imp.total_filas,
        'total_procesadas': imp.total_procesadas,
        'total_nuevos': imp.total_nuevos,
        'total_actualizados': imp.total_actualizados,
        'total_sin_cambio': imp.total_sin_cambio,
        'total_errores': imp.total_errores,
        'mensaje_error': imp.mensaje_error,
        'bloqueados': Producto.objects.filter(venta_bloqueada=True).count(),
    })


@cajero_required
def hub_importar_detalle(request, importacion_id):
    """Totales + log expandible de cambios / errores de una importación."""
    from decimal import Decimal

    from apps.tienda.models import ImportacionCatalogo, LogCambioImportacion
    from apps.tienda.precios import con_igv

    from apps.tienda.importers.makita_excel import _totales_desde_log

    imp = get_object_or_404(ImportacionCatalogo, pk=importacion_id)
    tipo_filtro = request.GET.get('tipo', '').strip()
    qs = LogCambioImportacion.objects.filter(importacion=imp).order_by('id')
    if tipo_filtro:
        qs = qs.filter(tipo_cambio=tipo_filtro)

    # Totales desde el log (evita desfase si se reanudó o hubo corridas previas)
    total_filas = imp.total_filas or 0
    nuevos_log, act_log, igual_log, err_log = _totales_desde_log(imp.pk, total_filas)
    # Si el log tiene datos y el resumen guardado no cuadra, mostrar el del log
    resumen_desfasado = (
        LogCambioImportacion.objects.filter(importacion=imp).exists()
        and (
            imp.total_nuevos != nuevos_log
            or imp.total_actualizados != act_log
            or imp.total_errores != err_log
        )
    )
    if resumen_desfasado or (nuevos_log or act_log or err_log):
        total_nuevos = nuevos_log
        total_actualizados = act_log
        total_sin_cambio = igual_log
        total_errores = err_log
        if resumen_desfasado and imp.estado == 'completada':
            ImportacionCatalogo.objects.filter(pk=imp.pk).update(
                total_nuevos=nuevos_log,
                total_actualizados=act_log,
                total_sin_cambio=igual_log,
                total_errores=err_log,
            )
    else:
        total_nuevos = imp.total_nuevos
        total_actualizados = imp.total_actualizados
        total_sin_cambio = imp.total_sin_cambio
        total_errores = imp.total_errores

    page = Paginator(qs, 80).get_page(request.GET.get('page'))
    codigos = [c.codigo_articulo for c in page.object_list if c.codigo_articulo]
    nombres_por_sku = {}
    if codigos:
        from apps.tienda.models import Producto
        nombres_por_sku = dict(
            Producto.objects.filter(codigo_articulo__in=codigos)
            .values_list('codigo_articulo', 'nombre')
        )

    filas_detalle = []
    for c in page.object_list:
        nombre = nombres_por_sku.get(c.codigo_articulo) or ''
        # Fallback: en alta/cambio de nombre el log ya trae el texto
        if not nombre:
            if c.campo in ('nombre', 'alta') and c.valor_nuevo:
                nombre = c.valor_nuevo
            elif c.tipo_cambio == 'nuevo' and c.valor_nuevo:
                nombre = c.valor_nuevo
        row = {
            'obj': c,
            'nombre': nombre,
            'lista_ant': None,
            'lista_nue': None,
            'igv_ant': None,
            'igv_nue': None,
        }
        if c.campo == 'precio_venta':
            try:
                if c.valor_anterior:
                    row['lista_ant'] = Decimal(c.valor_anterior)
                    row['igv_ant'] = con_igv(row['lista_ant'])
                if c.valor_nuevo:
                    row['lista_nue'] = Decimal(c.valor_nuevo)
                    row['igv_nue'] = con_igv(row['lista_nue'])
            except Exception:
                pass
        filas_detalle.append(row)

    return render(request, 'pos/hub_importar_detalle.html', {
        'imp': imp,
        'page_obj': page,
        'filas_detalle': filas_detalle,
        'tipo_filtro': tipo_filtro,
        'tipos': LogCambioImportacion.TIPO_CHOICES,
        'total_nuevos': total_nuevos,
        'total_actualizados': total_actualizados,
        'total_sin_cambio': total_sin_cambio,
        'total_errores': total_errores,
        'total_cambios_log': LogCambioImportacion.objects.filter(importacion=imp).count(),
        'total_importados': total_nuevos + total_actualizados + total_sin_cambio,
    })


@cajero_required
@require_http_methods(['POST'])
def hub_caja_movimiento(request):
    """Registrar ingreso (sencillo) o egreso (alquiler, etc.) en la caja abierta."""
    from decimal import Decimal, InvalidOperation
    from django.urls import reverse

    from apps.pos.models import CajaSesion, MovimientoCaja
    from apps.sistema.activity import registrar_actividad

    sesion = CajaSesion.objects.filter(
        cajero=request.user, estado=CajaSesion.ESTADO_ABIERTA
    ).first()
    next_url = request.POST.get('next') or reverse('pos:hub_inicio')
    if not sesion:
        messages.error(request, 'No tienes caja abierta. Ábrela antes de registrar movimientos.')
        return redirect('pos:hub_inicio')

    tipo = request.POST.get('tipo', '').strip()
    motivo = request.POST.get('motivo', MovimientoCaja.MOTIVO_OTRO).strip()
    concepto = request.POST.get('concepto', '').strip()[:255]
    try:
        monto = Decimal(str(request.POST.get('monto', '0')).replace(',', '.'))
    except (InvalidOperation, TypeError):
        monto = Decimal('0')

    motivos_ok = {m[0] for m in MovimientoCaja.MOTIVO_CHOICES}
    if tipo not in (MovimientoCaja.TIPO_INGRESO, MovimientoCaja.TIPO_EGRESO):
        messages.error(request, 'Indica si es ingreso o egreso.')
        return redirect(next_url)
    if motivo not in motivos_ok:
        motivo = MovimientoCaja.MOTIVO_OTRO
    if monto <= 0:
        messages.error(request, 'El monto debe ser mayor a cero.')
        return redirect(next_url)

    if motivo == MovimientoCaja.MOTIVO_SENCILLO:
        tipo = MovimientoCaja.TIPO_INGRESO
    elif motivo in (
        MovimientoCaja.MOTIVO_ALQUILER,
        MovimientoCaja.MOTIVO_SERVICIOS,
        MovimientoCaja.MOTIVO_RETIRO,
    ):
        tipo = MovimientoCaja.TIPO_EGRESO

    motivo_label = dict(MovimientoCaja.MOTIVO_CHOICES).get(motivo, motivo)
    MovimientoCaja.objects.create(
        sesion=sesion,
        tipo=tipo,
        motivo=motivo,
        monto=monto,
        concepto=concepto or motivo_label,
        registrado_por=request.user,
    )
    registrar_actividad(
        request, tipo='venta',
        accion=f'Caja {dict(MovimientoCaja.TIPO_CHOICES).get(tipo, tipo).lower()}',
        detalle=f'#{sesion.id} · {motivo_label} · S/ {monto}',
    )
    messages.success(
        request,
        f'Registrado: {dict(MovimientoCaja.TIPO_CHOICES).get(tipo)} S/ {monto} ({motivo_label}).',
    )
    return redirect(next_url)


@cajero_required
@require_http_methods(['POST'])
def hub_importar_cancelar(request, importacion_id):
    from django.utils import timezone
    from apps.tienda.models import ImportacionCatalogo, Producto

    imp = get_object_or_404(ImportacionCatalogo, pk=importacion_id)
    if imp.estado not in ('pendiente', 'procesando'):
        messages.info(request, 'Esa importación ya no está activa.')
        return redirect('pos:hub_importar')
    imp.estado = ImportacionCatalogo.ESTADO_ERROR
    imp.mensaje_error = 'Cancelada manualmente.'
    imp.fecha_fin = timezone.now()
    imp.save(update_fields=['estado', 'mensaje_error', 'fecha_fin'])
    Producto.objects.filter(venta_bloqueada=True).update(venta_bloqueada=False)
    messages.success(request, f'Importación #{imp.id} cancelada. Ya puedes subir otro archivo.')
    return redirect('pos:hub_importar')


@cajero_required
@require_http_methods(['POST'])
def hub_importar_reanudar(request, importacion_id):
    from apps.tienda.importers.makita_excel import iniciar_importacion_en_background
    from apps.tienda.models import ImportacionCatalogo

    imp = get_object_or_404(ImportacionCatalogo, pk=importacion_id)
    if not imp.archivo:
        messages.error(request, 'No hay archivo guardado. Sube el Excel de nuevo.')
        return redirect('pos:hub_importar')
    if ImportacionCatalogo.objects.filter(
        estado__in=['pendiente', 'procesando']
    ).exclude(pk=imp.pk).exists():
        messages.error(request, 'Ya hay otra importación en curso.')
        return redirect('pos:hub_importar')
    imp.estado = ImportacionCatalogo.ESTADO_PENDIENTE
    imp.mensaje_error = ''
    imp.save(update_fields=['estado', 'mensaje_error'])
    iniciar_importacion_en_background(imp.pk)
    messages.success(request, f'Reanudando importación #{imp.id}…')
    return redirect('pos:hub_importar')


@cajero_required
def hub_consulta_documento(request):
    """GET ?numero=45892156 → JSON con nombre / razón social."""
    from apps.sistema.consulta_peru import consultar_documento

    numero = (request.GET.get('numero') or '').strip()
    resultado = consultar_documento(numero)
    return JsonResponse(resultado.as_dict())


@cajero_required
def hub_salir(request):
    """Pantalla para elegir: solo salir, o cerrar caja + salir."""
    from decimal import Decimal
    from django.db.models import Sum

    from apps.pagos.models import Pago
    from apps.pos.models import CajaSesion

    sesion = CajaSesion.objects.filter(
        cajero=request.user, estado=CajaSesion.ESTADO_ABIERTA
    ).first()
    resumen = None
    if sesion:
        pagos = Pago.objects.filter(
            pedido__caja_sesion=sesion, estado=Pago.ESTADO_APROBADO
        )
        total_efectivo = (
            pagos.filter(metodo=Pago.METODO_EFECTIVO).aggregate(t=Sum('monto'))['t']
            or Decimal('0.00')
        )
        resumen = {
            'sesion': sesion,
            'total_ventas': pagos.aggregate(t=Sum('monto'))['t'] or Decimal('0.00'),
            'esperado_caja': (
                sesion.monto_apertura + total_efectivo + sesion.total_movimientos_neto()
            ),
        }
    return render(request, 'pos/hub_salir.html', {
        'sesion_caja': sesion,
        'caja_resumen': resumen,
    })


@cajero_required
@require_http_methods(['POST'])
def hub_salir_confirmar(request):
    from django.contrib.auth import logout
    from django.utils import timezone
    from decimal import Decimal
    from django.db.models import Sum

    from apps.pagos.models import Pago
    from apps.pos.models import CajaSesion
    from apps.sistema.activity import registrar_actividad

    accion = request.POST.get('accion', 'sesion')  # sesion | caja_y_sesion
    sesion = CajaSesion.objects.filter(
        cajero=request.user, estado=CajaSesion.ESTADO_ABIERTA
    ).first()

    if accion == 'caja_y_sesion' and sesion:
        pagos = Pago.objects.filter(
            pedido__caja_sesion=sesion, estado=Pago.ESTADO_APROBADO
        )
        total_efectivo = (
            pagos.filter(metodo=Pago.METODO_EFECTIVO).aggregate(t=Sum('monto'))['t']
            or Decimal('0.00')
        )
        esperado = sesion.monto_apertura + total_efectivo + sesion.total_movimientos_neto()
        monto = request.POST.get('monto_cierre')
        try:
            monto_cierre = Decimal(str(monto)) if monto not in (None, '') else esperado
        except Exception:
            monto_cierre = esperado
        sesion.fecha_cierre = timezone.now()
        sesion.monto_cierre = monto_cierre
        sesion.estado = CajaSesion.ESTADO_CERRADA
        obs = (request.POST.get('observaciones') or '').strip()
        if obs:
            sesion.observaciones = (
                (sesion.observaciones or '') + f'\nCierre al salir: {obs}'
            ).strip()
        sesion.save()
        registrar_actividad(
            request, tipo='venta', accion='Cerrar caja y sesión',
            detalle=f'Caja #{sesion.id} · cierre S/ {monto_cierre}',
        )
        messages.success(request, f'Caja #{sesion.id} cerrada. Hasta luego.')
    else:
        registrar_actividad(
            request, tipo='logout', accion='Cerrar sesión (caja sigue abierta)',
            detalle=f'Caja #{sesion.id} permanece abierta' if sesion else 'Sin caja abierta',
        )
        if sesion:
            messages.info(
                request,
                f'Tu sesión de caja #{sesion.id} sigue abierta. Puedes retomarla al volver a entrar.',
            )

    logout(request)
    return redirect('pos:login')


def _solo_superuser(user):
    return user.is_authenticated and user.is_superuser


@cajero_required
def hub_respaldo(request):
    if not _solo_superuser(request.user):
        messages.error(request, 'Solo el superusuario puede gestionar respaldos.')
        return redirect('pos:hub_inicio')
    from apps.mantenimiento.models import ContadorOT
    contador = ContadorOT.get_solo()
    return render(request, 'pos/hub_respaldo.html', {
        'contador_ot': contador,
        'proximo_ot': contador.proximo,
    })


@cajero_required
@require_http_methods(['POST'])
def hub_configurar_ot_correlativo(request):
    """Define el número con el que empezará / seguirá el correlativo OT-."""
    if not _solo_superuser(request.user):
        messages.error(request, 'Solo el superusuario puede configurar el correlativo OT.')
        return redirect('pos:hub_inicio')

    from apps.mantenimiento.models import ContadorOT
    from apps.sistema.activity import registrar_actividad

    raw = (request.POST.get('proximo_ot') or '').strip()
    try:
        proximo = int(raw)
        if proximo < 1:
            raise ValueError('debe ser >= 1')
    except (TypeError, ValueError):
        messages.error(request, 'Indica un número entero válido (ej. 700).')
        return redirect('pos:hub_respaldo')

    contador = ContadorOT.configurar_proximo(proximo)
    registrar_actividad(
        request,
        tipo='sistema',
        accion='Configurar correlativo OT',
        detalle=f'Siguiente OT-{contador.proximo} (último emitido {contador.ultimo})',
    )
    messages.success(
        request,
        f'Correlativo actualizado. La próxima OT será OT-{contador.proximo}.',
    )
    return redirect('pos:hub_respaldo')


@cajero_required
@require_http_methods(['GET'])
def hub_respaldo_exportar(request):
    if not _solo_superuser(request.user):
        return JsonResponse({'error': 'Sin permiso'}, status=403)
    from apps.sistema.views import exportar_base_datos
    from apps.sistema.activity import registrar_actividad
    registrar_actividad(request, tipo='sistema', accion='Exportar respaldo JSON', detalle='')
    return exportar_base_datos(request)


@cajero_required
@require_http_methods(['POST'])
def hub_respaldo_importar(request):
    if not _solo_superuser(request.user):
        messages.error(request, 'Sin permiso.')
        return redirect('pos:hub_inicio')

    archivo = request.FILES.get('archivo')
    confirmar = request.POST.get('confirmar') == 'on'

    if not archivo:
        messages.error(request, 'Selecciona un archivo JSON de respaldo.')
        return redirect('pos:hub_respaldo')
    if not confirmar:
        messages.error(request, 'Debes confirmar la importación.')
        return redirect('pos:hub_respaldo')
    if not archivo.name.lower().endswith('.json'):
        messages.error(request, 'El archivo debe ser .json.')
        return redirect('pos:hub_respaldo')

    import json
    import os
    import tempfile
    from django.core.management import call_command
    from apps.sistema.activity import registrar_actividad

    try:
        raw = archivo.read().decode('utf-8')
        json.loads(raw)
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as fh:
            fh.write(raw)
            tmp_path = fh.name
        try:
            call_command('loaddata', tmp_path, verbosity=0)
        finally:
            os.unlink(tmp_path)
        registrar_actividad(
            request, tipo='sistema', accion='Importar respaldo JSON',
            detalle=archivo.name,
        )
        messages.success(request, 'Importación completada correctamente.')
    except Exception as exc:
        messages.error(request, f'Error al importar: {exc}')
    return redirect('pos:hub_respaldo')


@cajero_required
@require_http_methods(['POST'])
def hub_reiniciar_operativo(request):
    """Borra ventas/pagos/movimientos/OT y pone stock en 0. No toca productos."""
    if not _solo_superuser(request.user):
        messages.error(request, 'Solo el superusuario puede reiniciar data operativa.')
        return redirect('pos:hub_inicio')

    frase = (request.POST.get('confirmacion') or '').strip().upper()
    if frase != 'REINICIAR':
        messages.error(request, 'Para confirmar debes escribir exactamente: REINICIAR')
        return redirect('pos:hub_respaldo')

    if request.POST.get('confirmar_check') != 'on':
        messages.error(request, 'Marca la casilla de confirmación.')
        return redirect('pos:hub_respaldo')

    from apps.sistema.reset_operativo import reiniciar_data_operativa
    from apps.sistema.activity import registrar_actividad

    keep_import = request.POST.get('keep_import_logs') == 'on'

    try:
        stats = reiniciar_data_operativa(
            wipe_import_logs=not keep_import,
        )
        detalle = ', '.join(f'{k}={v}' for k, v in stats.items())
        registrar_actividad(
            request, tipo='sistema', accion='Reiniciar data operativa', detalle=detalle[:500],
        )
        messages.success(
            request,
            'Data operativa reiniciada. Productos y clientes conservados; stock en 0. '
            'El correlativo OT no se modifica (configúralo arriba si hace falta).',
        )
        messages.info(request, f'Detalle: {detalle[:400]}')
    except Exception as exc:
        messages.error(request, f'No se pudo reiniciar: {exc}')
    return redirect('pos:hub_respaldo')


@cajero_required
@require_http_methods(['POST'])
def hub_inventario_ingreso_rapido(request):
    """Ingreso rápido de stock desde la pantalla de venta POS (modal sin salir de caja)."""
    import json
    from django.db import transaction
    from apps.inventario.models import MovimientoInventario
    from apps.sistema.activity import registrar_actividad
    from apps.tienda.models import Producto

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    try:
        producto_id = int(data.get('producto_id'))
        cantidad = int(data.get('cantidad', 1))
        motivo_text = (data.get('motivo') or 'Ingreso rápido para venta POS').strip()
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Datos de producto o cantidad inválidos'}, status=400)

    if cantidad <= 0:
        return JsonResponse({'ok': False, 'error': 'La cantidad a ingresar debe ser mayor a 0'}, status=400)

    with transaction.atomic():
        producto = Producto.objects.select_for_update().filter(pk=producto_id).first()
        if not producto:
            return JsonResponse({'ok': False, 'error': 'Producto no encontrado'}, status=404)

        prev_stock = producto.stock
        producto.stock += cantidad
        producto.save(update_fields=['stock'])

        # Registrar movimiento de inventario formal
        try:
            MovimientoInventario.objects.create(
                producto=producto,
                tipo=MovimientoInventario.TIPO_ENTRADA,
                motivo=MovimientoInventario.MOTIVO_AJUSTE,
                cantidad=cantidad,
                usuario=request.user,
                notas=f'Ingreso rápido desde POS: {motivo_text} (Stock anterior: {prev_stock} -> nuevo: {producto.stock})',
            )
        except Exception:
            pass

        registrar_actividad(
            request,
            tipo='inventario',
            accion=f'Ingreso rápido POS (+{cantidad} und)',
            detalle=f'{producto.codigo_articulo} - {producto.nombre}. Stock: {prev_stock} -> {producto.stock}',
        )

    return JsonResponse({
        'ok': True,
        'producto_id': producto.id,
        'codigo_articulo': producto.codigo_articulo,
        'nombre': producto.nombre,
        'stock_tienda': producto.stock,
        'stock_web': producto.stock_web,
        'stock_disponible': producto.stock + producto.stock_web,
        'mensaje': f'Se agregaron {cantidad} unidad(es) al stock de tienda ({producto.codigo_articulo}).',
    })

