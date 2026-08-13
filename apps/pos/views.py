import json
import csv
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db import transaction, models
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.urls import reverse, reverse_lazy
from django.conf import settings

from apps.pos.models import CajaSesion, TicketPOS
from apps.pedidos.models import Pedido, DetallePedido
from apps.clientes.models import Cliente
from apps.tienda.models import Producto
from apps.pagos.models import Pago
from apps.inventario.models import MovimientoInventario
from apps.pedidos.services import confirmar_pago_pedido
from apps.mantenimiento.models import EquipoRegistrado
import datetime


class PosLoginView(LoginView):
    """Login propio del POS: mismos usuarios/contraseñas que admin."""
    template_name = 'pos/login.html'
    redirect_authenticated_user = True
    extra_context = {'negocio': getattr(settings, 'NEGOCIO', {})}

    def get_success_url(self):
        url = self.get_redirect_url()
        if url:
            return url
        user = self.request.user
        if getattr(user, 'rol', None) == getattr(user, 'ROLE_TECNICO', 'tecnico') and not user.is_superuser:
            return reverse_lazy('mantenimiento:dashboard')
        return reverse_lazy('pos:hub_inicio')

    def form_valid(self, form):
        from apps.sistema.internal_access import is_staff_interno

        user = form.get_user()
        if not is_staff_interno(user):
            form.add_error(
                None,
                'Esta cuenta no tiene acceso al sistema interno.',
            )
            return self.form_invalid(form)
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        from apps.sistema.internal_access import is_staff_interno, puede_usar_pos

        if request.user.is_authenticated and is_staff_interno(request.user):
            if puede_usar_pos(request.user) or request.user.is_superuser:
                return redirect('pos:hub_inicio')
            if getattr(request.user, 'rol', None) == getattr(request.user, 'ROLE_TECNICO', 'tecnico'):
                return redirect('mantenimiento:dashboard')
        return super().dispatch(request, *args, **kwargs)


def cajero_required(view_func):
    """Acceso solo staff interno (vendedor/admin). No forma parte de la tienda web."""
    def _wrapped_view(request, *args, **kwargs):
        from apps.sistema.internal_access import (
            ocultar_sistema_interno,
            puede_usar_pos,
            redirect_pos_login,
        )

        if not request.user.is_authenticated:
            return redirect_pos_login(request)
        if not puede_usar_pos(request.user):
            # Cliente u otro rol: no revelar el POS
            return ocultar_sistema_interno(request)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def _productos_vitrina_pos(limit=12):
    """
    Catálogo inicial liviano: servicios + carbones/escobillas + últimos agregados.
    El resto se carga con búsqueda AJAX.
    """
    base = Producto.objects.filter(activo=True, venta_bloqueada=False).select_related('categoria')
    servicios = list(base.filter(tipo=Producto.TIPO_SERVICIO).order_by('-fecha_creacion')[:4])
    ids = {p.id for p in servicios}
    carbones = list(
        base.filter(
            models.Q(nombre__icontains='carbon')
            | models.Q(nombre__icontains='carbón')
            | models.Q(nombre__icontains='escobilla')
        ).exclude(id__in=ids).order_by('nombre')[:5]
    )
    ids.update({p.id for p in carbones})
    recientes = list(
        base.exclude(id__in=ids).order_by('-fecha_creacion')[: max(0, limit - len(servicios) - len(carbones))]
    )
    return servicios + carbones + recientes


@cajero_required
def pos_dashboard(request):
    sesion = CajaSesion.objects.filter(cajero=request.user, estado=CajaSesion.ESTADO_ABIERTA).first()
    if not sesion:
        return redirect('pos:abrir_caja')

    productos = _productos_vitrina_pos(12)
    from apps.tienda.models import Categoria
    categorias = Categoria.objects.all().order_by('nombre')
    bloqueados = Producto.objects.filter(venta_bloqueada=True).count()

    context = {
        'sesion': sesion,
        'productos': productos,
        'categorias': categorias,
        'bloqueados_import': bloqueados,
        'is_pos': True,
    }
    return render(request, 'pos/dashboard.html', context)

@cajero_required
def abrir_caja(request):
    # Check if cashier already has an open session
    sesion = CajaSesion.objects.filter(cajero=request.user, estado=CajaSesion.ESTADO_ABIERTA).first()
    if sesion:
        return redirect('pos:dashboard')

    from apps.sistema.models import Empresa, Sede
    sedes = list(request.user.sedes_permitidas())
    if not sedes:
        sedes = list(Sede.objects.filter(activa=True))
    if not sedes:
        # Bootstrap mínimo (tests / primera instalación)
        empresa, _ = Empresa.objects.get_or_create(
            ruc='10431549001',
            defaults={'nombre': 'STA El Charly Makita', 'nombre_corto': 'El Charly'},
        )
        tienda, _ = Sede.objects.get_or_create(
            codigo='tienda',
            defaults={
                'empresa': empresa, 'nombre': 'Tienda ASPYME',
                'tipo': Sede.TIPO_TIENDA, 'compartir_productos': True, 'orden': 1,
            },
        )
        taller, _ = Sede.objects.get_or_create(
            codigo='taller',
            defaults={
                'empresa': empresa, 'nombre': 'Taller',
                'tipo': Sede.TIPO_TALLER, 'compartir_productos': True, 'orden': 2,
            },
        )
        sedes = [tienda, taller]
        if request.user.pk:
            request.user.sedes.add(tienda, taller)

    if request.method == 'POST':
        monto_apertura = Decimal(request.POST.get('monto_apertura', '0.00'))
        observaciones = request.POST.get('observaciones', '')
        sede_id = request.POST.get('sede_id')
        sede = None
        if sede_id:
            sede = next((s for s in sedes if str(s.id) == str(sede_id)), None)
        if not sede and sedes:
            sede = sedes[0]
        if not sede:
            from django.contrib import messages
            messages.error(request, 'Debes elegir una sede para abrir caja.')
            return render(request, 'pos/abrir_caja.html', {'sedes': sedes})

        CajaSesion.objects.create(
            cajero=request.user,
            sede=sede,
            monto_apertura=monto_apertura,
            estado=CajaSesion.ESTADO_ABIERTA,
            observaciones=observaciones,
        )
        request.user.sede_activa = sede
        request.user.save(update_fields=['sede_activa'])
        return redirect('pos:dashboard')

    return render(request, 'pos/abrir_caja.html', {'sedes': sedes})

@cajero_required
def cerrar_caja(request, sesion_id):
    sesion = get_object_or_404(CajaSesion, id=sesion_id)
    
    # Restrict closure to the owner of the box or an administrator
    if sesion.cajero != request.user and not request.user.is_superuser and request.user.rol != request.user.ROLE_ADMIN:
        raise PermissionDenied("No tiene permisos para cerrar esta sesión de caja.")

    # Calculate expected figures
    pagos_aprobados = Pago.objects.filter(pedido__caja_sesion=sesion, estado=Pago.ESTADO_APROBADO)
    
    total_efectivo = pagos_aprobados.filter(metodo=Pago.METODO_EFECTIVO).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    total_yape = pagos_aprobados.filter(metodo=Pago.METODO_YAPE).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    total_plin = pagos_aprobados.filter(metodo=Pago.METODO_PLIN).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    total_tarjeta = pagos_aprobados.filter(metodo=Pago.METODO_TARJETA).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    total_transferencia = pagos_aprobados.filter(metodo=Pago.METODO_TRANSFERENCIA).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    
    total_ventas = total_efectivo + total_yape + total_plin + total_tarjeta + total_transferencia
    neto_movimientos = sesion.total_movimientos_neto()
    total_esperado_caja = sesion.monto_apertura + total_efectivo + neto_movimientos
    movimientos = sesion.movimientos.select_related('registrado_por').all()
    total_ingresos_caja = sum(
        (m.monto for m in movimientos if m.tipo == 'ingreso'),
        Decimal('0.00'),
    )
    total_egresos_caja = sum(
        (m.monto for m in movimientos if m.tipo == 'egreso'),
        Decimal('0.00'),
    )

    if request.method == 'POST' and sesion.estado == CajaSesion.ESTADO_ABIERTA:
        monto_cierre = Decimal(request.POST.get('monto_cierre', '0.00'))
        observaciones = request.POST.get('observaciones', '')
        
        sesion.fecha_cierre = timezone.now()
        sesion.monto_cierre = monto_cierre
        sesion.estado = CajaSesion.ESTADO_CERRADA
        sesion.observaciones = observaciones
        sesion.save()
        
        return redirect('pos:cerrar_caja', sesion_id=sesion.id)

    diferencia = Decimal('0.00')
    if sesion.monto_cierre is not None:
        diferencia = sesion.monto_cierre - total_esperado_caja

    # Fetch list of tickets emitted
    tickets = TicketPOS.objects.filter(pedido__caja_sesion=sesion)

    context = {
        'sesion': sesion,
        'total_efectivo': total_efectivo,
        'total_yape': total_yape,
        'total_plin': total_plin,
        'total_tarjeta': total_tarjeta,
        'total_transferencia': total_transferencia,
        'total_ventas': total_ventas,
        'total_esperado_caja': total_esperado_caja,
        'total_ingresos_caja': total_ingresos_caja,
        'total_egresos_caja': total_egresos_caja,
        'movimientos_caja': movimientos,
        'diferencia': diferencia,
        'tickets': tickets,
    }
    return render(request, 'pos/cierre_caja_detalle.html', context)

def buscar_productos(request):
    """Catálogo para POS y cotizaciones: herramientas, accesorios y repuestos."""
    from apps.sistema.stock import stock_para_venta
    from apps.sistema.internal_access import (
        is_staff_interno,
        ocultar_sistema_interno,
        redirect_pos_login,
    )
    from apps.pos.models import CajaSesion

    if not request.user.is_authenticated:
        return redirect_pos_login(request)
    if not is_staff_interno(request.user):
        return ocultar_sistema_interno(request)

    query = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '')
    categoria_id = request.GET.get('categoria', '')
    # Por defecto no mostrar bloqueados; si se pide explícito, incluir con flag
    incluir_bloqueados = request.GET.get('incluir_bloqueados') == '1'
    productos = Producto.objects.filter(activo=True).select_related('categoria')
    if not incluir_bloqueados:
        productos = productos.filter(venta_bloqueada=False)

    sesion = CajaSesion.objects.filter(
        cajero=request.user, estado=CajaSesion.ESTADO_ABIERTA
    ).select_related('sede').first()
    sede = sesion.sede if sesion else None

    def _row(p):
        return {
            'id': p.id,
            'codigo_articulo': p.codigo_display,
            'nombre': p.nombre,
            'modelo': p.modelo or '',
            'voltaje': p.voltaje or '',
            'precio_venta': str(p.precio_venta),
            'precio_lista': str(p.precio_venta),
            'precio_costo': str(p.precio_costo or 0),
            'precio_con_igv': str(p.precio_lista_con_igv),
            'precio_web': str(p.precio_publico),
            'stock': p.stock,
            'stock_web': p.stock_web,
            'stock_disponible': stock_para_venta(p, sede),
            'tipo': p.tipo,
            'categoria_id': p.categoria_id or '',
            'categoria': p.categoria.nombre if p.categoria else '',
            'imagen': p.imagen_principal.url if p.imagen_principal else '',
            'venta_bloqueada': p.venta_bloqueada,
            'status_sap': p.status_sap or '',
            'lima_label': p.disponibilidad_lima_label,
            'lima_css': p.disponibilidad_lima_css,
        }

    if query:
        from apps.tienda.search import filtrar_productos
        productos = filtrar_productos(productos, query)
    elif not tipo and not categoria_id:
        # Sin búsqueda: devolver vitrina representativa (no 22k)
        vitrina = _productos_vitrina_pos(12)
        return JsonResponse({
            'productos': [_row(p) for p in vitrina],
            'modo': 'vitrina',
        })

    if tipo in ('herramienta', 'accesorio', 'repuesto', 'servicio'):
        productos = productos.filter(tipo=tipo)
    if categoria_id.isdigit():
        productos = productos.filter(categoria_id=int(categoria_id))

    data = [_row(p) for p in productos.order_by('nombre')[:40]]
    return JsonResponse({'productos': data, 'modo': 'busqueda'})

@cajero_required
@transaction.atomic
def registrar_venta(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)

    sesion = CajaSesion.objects.filter(cajero=request.user, estado=CajaSesion.ESTADO_ABIERTA).first()
    if not sesion:
        return JsonResponse({'success': False, 'error': 'No hay sesión de caja abierta.'}, status=400)

    try:
        # JSON o multipart (voucher / combinado)
        if request.content_type and 'multipart/form-data' in request.content_type:
            raw_items = request.POST.get('items', '[]')
            data = {
                'cliente_varios': request.POST.get('cliente_varios'),
                'cliente_dni_ruc': request.POST.get('cliente_dni_ruc', ''),
                'cliente_nombre': request.POST.get('cliente_nombre', ''),
                'cliente_telefono': request.POST.get('cliente_telefono', ''),
                'cliente_correo': request.POST.get('cliente_correo', ''),
                'cliente_direccion': request.POST.get('cliente_direccion', ''),
                'metodo_pago': request.POST.get('metodo_pago', 'efectivo'),
                'tipo_comprobante': request.POST.get('tipo_comprobante', 'ticket'),
                'descuento': request.POST.get('descuento', '0.00'),
                'items': json.loads(raw_items) if isinstance(raw_items, str) else raw_items,
                'pago_combinado': request.POST.get('pago_combinado', ''),
                'idempotency_key': request.POST.get('idempotency_key', ''),
                'fecha_venta': request.POST.get('fecha_venta', ''),
            }
            voucher_file = request.FILES.get('voucher')
        else:
            data = json.loads(request.body)
            voucher_file = None

        # Evita doble cobro si el navegador reintenta tras un corte corto (failover 4G).
        idem = (data.get('idempotency_key') or '').strip()[:64]
        session_idem_key = None
        if idem:
            session_idem_key = f'pos_venta_idem:{idem}'
            cached = request.session.get(session_idem_key)
            if cached:
                return JsonResponse(cached)

        dni_ruc = data.get('cliente_dni_ruc', '').strip()
        nombre = data.get('cliente_nombre', '').strip()
        telefono = data.get('cliente_telefono', '').strip()
        correo = data.get('cliente_correo', '').strip()
        direccion = data.get('cliente_direccion', '').strip()

        metodo_pago = data.get('metodo_pago', 'efectivo')
        tipo_comprobante = data.get('tipo_comprobante', 'ticket')
        descuento_general = Decimal(str(data.get('descuento', '0.00') or '0'))
        items = data.get('items', [])

        if tipo_comprobante != TicketPOS.TIPO_TICKET:
            return JsonResponse({
                'success': False,
                'error': (
                    'Por ahora solo se emiten tickets/recibos internos. '
                    'Boleta y factura se registrarán manualmente hasta integrar CPE.'
                ),
            }, status=400)

        metodos_ok = {
            Pago.METODO_EFECTIVO, Pago.METODO_YAPE, Pago.METODO_PLIN,
            Pago.METODO_TARJETA, Pago.METODO_TRANSFERENCIA, 'combinado',
        }
        if metodo_pago not in metodos_ok:
            return JsonResponse({'success': False, 'error': 'Método de pago inválido.'}, status=400)

        # Pago combinado: [{metodo, monto}, {metodo, monto}]
        partes_combinado = []
        if metodo_pago == 'combinado':
            raw_comb = data.get('pago_combinado') or '[]'
            if isinstance(raw_comb, str):
                try:
                    partes_combinado = json.loads(raw_comb)
                except json.JSONDecodeError:
                    partes_combinado = []
            else:
                partes_combinado = raw_comb
            if len(partes_combinado) != 2:
                return JsonResponse({
                    'success': False,
                    'error': 'Pago combinado requiere exactamente 2 métodos con monto.',
                }, status=400)
            for parte in partes_combinado:
                m = parte.get('metodo')
                if m not in {
                    Pago.METODO_EFECTIVO, Pago.METODO_YAPE, Pago.METODO_PLIN,
                    Pago.METODO_TARJETA, Pago.METODO_TRANSFERENCIA,
                }:
                    return JsonResponse({'success': False, 'error': f'Método inválido en combinado: {m}'}, status=400)

        if not items:
            return JsonResponse({'success': False, 'error': 'El carrito está vacío. Agrega al menos un producto.'}, status=400)

        hoy_lima = timezone.localdate()
        es_historica = False
        fecha_historica = None
        raw_fecha = (data.get('fecha_venta') or '').strip()
        if raw_fecha:
            fecha_historica = parse_date(raw_fecha)
            if not fecha_historica:
                return JsonResponse({
                    'success': False,
                    'error': 'Fecha de venta inválida. Usa el formato dd/mm/aaaa del selector.',
                }, status=400)
            if fecha_historica > hoy_lima:
                return JsonResponse({
                    'success': False,
                    'error': 'No se puede registrar una venta con fecha futura.',
                }, status=400)
            es_historica = fecha_historica < hoy_lima

        if es_historica:
            fecha_pedido_dt = timezone.make_aware(
                datetime.datetime.combine(fecha_historica, datetime.time(12, 0)),
                timezone.get_current_timezone(),
            )
        else:
            fecha_pedido_dt = timezone.now()

        # SUNAT: en boletas < S/700 se admite consumidor final; usamos 00000000 / Cliente Varios.
        CLIENTE_VARIOS_DNI = '00000000'
        usar_varios = data.get('cliente_varios') in (True, 'true', '1', 1)
        if usar_varios or dni_ruc == CLIENTE_VARIOS_DNI:
            dni_ruc = CLIENTE_VARIOS_DNI
            nombre = nombre or 'Cliente Varios / Consumidor final'
        else:
            if not dni_ruc or len(dni_ruc) not in (8, 11) or not dni_ruc.isdigit():
                return JsonResponse({
                    'success': False,
                    'error': 'Indica DNI (8) o RUC (11), o marca «Cliente varios».',
                }, status=400)
            if not nombre:
                return JsonResponse({
                    'success': False,
                    'error': 'Indica el nombre del cliente (o usa Cliente varios).',
                }, status=400)

        sede = sesion.sede
        if not sede:
            return JsonResponse({
                'success': False,
                'error': 'La caja no tiene sede asignada. Cierra y abre caja eligiendo sede.',
            }, status=400)

        # 1. Fetch or Create Client
        if dni_ruc == CLIENTE_VARIOS_DNI:
            cliente, _ = Cliente.objects.get_or_create(
                dni_ruc=CLIENTE_VARIOS_DNI,
                defaults={
                    'nombre_completo': 'Cliente Varios / Consumidor final',
                    'tipo': 'persona',
                    'canal_origen': Cliente.CANAL_POS,
                },
            )
        else:
            tipo_cliente = 'empresa' if len(dni_ruc) == 11 else 'persona'
            cliente, created = Cliente.objects.get_or_create(
                dni_ruc=dni_ruc,
                defaults={
                    'nombre_completo': nombre,
                    'tipo': tipo_cliente,
                    'telefono': telefono,
                    'correo': correo,
                    'direccion': direccion,
                    'canal_origen': Cliente.CANAL_POS,
                },
            )
            if not created:
                if nombre:
                    cliente.nombre_completo = nombre
                if telefono:
                    cliente.telefono = telefono
                if correo:
                    cliente.correo = correo
                if direccion:
                    cliente.direccion = direccion
                cliente.save()

        # 2. Check stock availability for all items before modifying database
        from apps.sistema.stock import stock_para_venta

        db_items = []
        total_acumulado = Decimal('0.00')

        for item in items:
            prod_id = item.get('id')
            cantidad = int(item.get('cantidad', 1))
            precio_custom = item.get('precio')
            series = item.get('series', [])

            producto = get_object_or_404(Producto, id=prod_id)
            if producto.venta_bloqueada:
                return JsonResponse({
                    'success': False,
                    'error': (
                        f'«{producto.nombre}» está bloqueado por una importación de catálogo en curso. '
                        'Espera a que termine o elige otro producto.'
                    ),
                }, status=400)
            disponible = stock_para_venta(producto, sede)
            if not es_historica and disponible < cantidad:
                return JsonResponse({
                    'success': False,
                    'error': (
                        f'Stock insuficiente para {producto.nombre} '
                        f'(Solicitado: {cantidad}, Disponible: {disponible})'
                    ),
                }, status=400)

            precio_final = (
                Decimal(str(precio_custom))
                if precio_custom is not None
                else producto.precio_lista_con_igv
            )
            item_subtotal = cantidad * precio_final
            total_acumulado += item_subtotal
            
            nota_item = (item.get('nota') or '').strip().upper()
            nombre_linea = f"{producto.nombre} - {nota_item}" if nota_item else producto.nombre

            db_items.append({
                'producto': producto,
                'cantidad': cantidad,
                'precio_final': precio_final,
                'subtotal': item_subtotal,
                'series': series,
                'nombre_linea': nombre_linea,
            })
            
        # Calculate totals
        total_final = max(Decimal('0.00'), total_acumulado - descuento_general)
        subtotal = total_final / Decimal('1.18')
        igv = total_final - subtotal

        # Validar pago combinado antes de escribir pedido
        if metodo_pago == 'combinado':
            try:
                a1 = Decimal(str(partes_combinado[0]['monto'])).quantize(Decimal('0.01'))
                a2 = Decimal(str(partes_combinado[1]['monto'])).quantize(Decimal('0.01'))
            except Exception:
                return JsonResponse({'success': False, 'error': 'Montos de pago combinado inválidos.'}, status=400)
            if a1 <= 0 or a2 <= 0:
                return JsonResponse({
                    'success': False,
                    'error': 'Cada parte del pago combinado debe ser mayor a cero.',
                }, status=400)
            if a1 + a2 != total_final:
                return JsonResponse({
                    'success': False,
                    'error': (
                        f'Los montos combinados (S/ {a1 + a2}) deben sumar el total '
                        f'(S/ {total_final}).'
                    ),
                }, status=400)
            partes_combinado[0]['monto'] = a1
            partes_combinado[1]['monto'] = a2
        
        # 3. Guardar Venta / Pedido
        pedido = Pedido.objects.create(
            canal=Pedido.CANAL_POS,
            cliente=cliente,
            estado=Pedido.ESTADO_ENTREGADO,
            subtotal=subtotal,
            igv=igv,
            total=total_final,
            atendido_por=request.user,
            caja_sesion=None if es_historica else sesion,
            sede=sede,
            fecha_pedido=fecha_pedido_dt,
            es_historica=es_historica,
            notas=(
                f"Venta histórica del cuaderno ({fecha_historica.strftime('%d/%m/%Y')}). "
                "No descuenta stock ni entra a la caja abierta."
                if es_historica
                else f"Venta POS registrada en sesión {sesion.id}"
            ),
        )
        
        # 4. Detalles + registro de equipos (series del cajero)
        for item_data in db_items:
            prod = item_data['producto']
            cant = item_data['cantidad']
            pre = item_data['precio_final']
            series = item_data['series']

            DetallePedido.objects.create(
                pedido=pedido,
                producto=prod,
                codigo_articulo=prod.codigo_articulo,
                nombre_producto=item_data['nombre_linea'],
                cantidad=cant,
                precio_unitario=pre,
                subtotal=item_data['subtotal'],
            )

            if prod.tipo == Producto.TIPO_HERRAMIENTA or prod.familia_sap == 'EQUIPOS':
                fecha_compra = fecha_historica if es_historica else timezone.now().date()
                garantia_hasta = fecha_compra + datetime.timedelta(days=365)

                for i in range(cant):
                    sn = (
                        series[i].strip()
                        if i < len(series) and series[i].strip()
                        else f"POS-{pedido.numero_pedido}-{prod.codigo_articulo}-{i+1}"
                    )
                    base_sn = sn
                    counter = 1
                    while EquipoRegistrado.objects.filter(numero_serie=sn).exists():
                        sn = f"{base_sn}-{counter}"
                        counter += 1

                    EquipoRegistrado.objects.create(
                        cliente=cliente,
                        pedido_origin=pedido,
                        producto=prod,
                        numero_serie=sn,
                        fecha_compra=fecha_compra,
                        garantia_hasta=garantia_hasta,
                        estado=EquipoRegistrado.ESTADO_ACTIVO,
                        origen=EquipoRegistrado.ORIGEN_NUESTRO,
                    )

        # 5. Pago(s) + inventario
        if metodo_pago == 'combinado':
            m1 = partes_combinado[0]['metodo']
            m2 = partes_combinado[1]['metodo']
            a1 = Decimal(str(partes_combinado[0]['monto']))
            a2 = Decimal(str(partes_combinado[1]['monto']))
            pago1 = Pago.objects.create(
                pedido=pedido,
                metodo=m1,
                monto=a1,
                estado=Pago.ESTADO_APROBADO,
                referencia_externa=f"POS-SES-{sesion.id}-PED-{pedido.id}-A",
            )
            pago2 = Pago.objects.create(
                pedido=pedido,
                metodo=m2,
                monto=a2,
                estado=Pago.ESTADO_APROBADO,
                referencia_externa=f"POS-SES-{sesion.id}-PED-{pedido.id}-B",
            )
            confirmar_pago_pedido(
                pedido=pedido,
                metodo=m1,
                monto=a1,
                pago=pago1,
                usuario=request.user,
                motivo_inventario=MovimientoInventario.MOTIVO_VENTA_POS,
                descontar_stock=not es_historica,
            )
            pagos_creados = [pago1, pago2]
        else:
            pago = confirmar_pago_pedido(
                pedido=pedido,
                metodo=metodo_pago,
                monto=total_final,
                referencia_externa=f"POS-SES-{sesion.id}-PED-{pedido.id}",
                usuario=request.user,
                motivo_inventario=MovimientoInventario.MOTIVO_VENTA_POS,
                descontar_stock=not es_historica,
            )
            pagos_creados = [pago]

        if voucher_file:
            try:
                from apps.tienda.images import convertir_a_webp
                webp = convertir_a_webp(voucher_file)
                target = pagos_creados[0]
                target.voucher.save(webp.name, webp, save=True)
                if not pedido.voucher:
                    pedido.voucher.save(webp.name, webp, save=True)
            except Exception:
                pagos_creados[0].voucher = voucher_file
                pagos_creados[0].save(update_fields=['voucher'])
        
        # 6. Create TicketPOS
        ticket = TicketPOS.objects.create(
            pedido=pedido,
            cajero=request.user,
            subtotal=subtotal,
            igv=igv,
            total=total_final,
            tipo_comprobante=TicketPOS.TIPO_TICKET,
            ruc_cliente=None,
            razon_social=None,
        )
        if es_historica:
            Pago.objects.filter(pedido=pedido).update(fecha_pago=fecha_pedido_dt)
            TicketPOS.objects.filter(pk=ticket.pk).update(fecha_emision=fecha_pedido_dt)
        
        from apps.sistema.activity import registrar_actividad
        registrar_actividad(
            request,
            tipo='venta',
            accion='Venta POS registrada',
            detalle=f'Pedido {pedido.numero_pedido} · S/ {pedido.total}',
        )
        payload = {
            'success': True,
            'ticket_id': ticket.id,
            'numero_serie': ticket.numero_serie,
            'total': str(ticket.total),
        }
        if session_idem_key:
            request.session[session_idem_key] = payload
            request.session.modified = True
        return JsonResponse(payload)

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Datos JSON inválidos.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@cajero_required
def imprimir_ticket(request, ticket_id):
    ticket = get_object_or_404(TicketPOS, id=ticket_id)
    # IDOR: solo el cajero dueño, admin o superuser
    if (
        ticket.cajero_id != request.user.id
        and not request.user.is_superuser
        and getattr(request.user, 'rol', None) != getattr(request.user, 'ROLE_ADMIN', 'admin')
    ):
        raise PermissionDenied('No puede ver este ticket.')
    detalles = ticket.pedido.detalles.all()

    if not ticket.impreso:
        ticket.impreso = True
        ticket.save()

    negocio = getattr(settings, 'NEGOCIO', {})
    context = {
        'ticket': ticket,
        'pedido': ticket.pedido,
        'detalles': detalles,
        'negocio': {
            'nombre': negocio.get('nombre', 'CHARLY MAKITA AREQUIPA'),
            'ruc': negocio.get('ruc', ''),
            'direccion': negocio.get('direccion', ''),
            'telefono': negocio.get('telefono', ''),
            'email': negocio.get('email', ''),
        },
    }
    return render(request, 'pos/ticket_impresion.html', context)

@cajero_required
def exportar_cierre_caja(request, sesion_id):
    sesion = get_object_or_404(CajaSesion, id=sesion_id)
    if (
        sesion.cajero_id != request.user.id
        and not request.user.is_superuser
        and getattr(request.user, 'rol', None) != getattr(request.user, 'ROLE_ADMIN', 'admin')
    ):
        raise PermissionDenied('No puede exportar este cierre de caja.')
    if sesion.estado == CajaSesion.ESTADO_ABIERTA:
        return HttpResponse("La sesión de caja debe estar cerrada para exportar el resumen.", status=400)
        
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="Cierre_Caja_Sesion_{sesion.id}.csv"'
    
    # Force UTF-8 BOM so Excel opens it with correct accents
    response.write(u'\ufeff'.encode('utf8'))
    
    writer = csv.writer(response)
    writer.writerow(['REPORTE DE CIERRE DE CAJA - SESIÓN #' + str(sesion.id)])
    writer.writerow([])
    writer.writerow(['Cajero', sesion.cajero.username])
    writer.writerow(['Fecha Apertura', sesion.fecha_apertura.strftime('%d/%m/%Y %H:%M:%S')])
    writer.writerow(['Fecha Cierre', sesion.fecha_cierre.strftime('%d/%m/%Y %H:%M:%S')])
    writer.writerow(['Estado', sesion.get_estado_display()])
    writer.writerow([])
    
    # Summary of totals
    pagos_aprobados = Pago.objects.filter(pedido__caja_sesion=sesion, estado=Pago.ESTADO_APROBADO)
    
    efectivo = pagos_aprobados.filter(metodo=Pago.METODO_EFECTIVO).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    yape = pagos_aprobados.filter(metodo=Pago.METODO_YAPE).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    plin = pagos_aprobados.filter(metodo=Pago.METODO_PLIN).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    tarjeta = pagos_aprobados.filter(metodo=Pago.METODO_TARJETA).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    transf = pagos_aprobados.filter(metodo=Pago.METODO_TRANSFERENCIA).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    
    total_ventas = efectivo + yape + plin + tarjeta + transf
    diferencia = sesion.monto_cierre - (sesion.monto_apertura + efectivo)
    
    writer.writerow(['CONCILIACIÓN FINANCIERA'])
    writer.writerow(['Monto de Apertura', f"S/. {sesion.monto_apertura:.2f}"])
    writer.writerow(['Ventas en Efectivo', f"S/. {efectivo:.2f}"])
    writer.writerow(['Total Esperado en Efectivo', f"S/. {(sesion.monto_apertura + efectivo):.2f}"])
    writer.writerow(['Monto de Cierre Físico', f"S/. {sesion.monto_cierre:.2f}"])
    writer.writerow(['Diferencia / Cuadre', f"S/. {diferencia:.2f}"])
    writer.writerow([])
    
    writer.writerow(['VENTAS POR MÉTODO DE PAGO'])
    writer.writerow(['Efectivo', f"S/. {efectivo:.2f}"])
    writer.writerow(['Yape', f"S/. {yape:.2f}"])
    writer.writerow(['Plin', f"S/. {plin:.2f}"])
    writer.writerow(['Tarjeta Crédito/Débito', f"S/. {tarjeta:.2f}"])
    writer.writerow(['Transferencia Bancaria', f"S/. {transf:.2f}"])
    writer.writerow(['Total Ventas del Día', f"S/. {total_ventas:.2f}"])
    writer.writerow([])
    
    # Detailed list of sales
    writer.writerow(['DETALLE DE VENTAS'])
    writer.writerow(['Nro. Comprobante', 'Cliente', 'DNI/RUC', 'Canal', 'Fecha/Hora', 'Subtotal', 'IGV', 'Total', 'Método Pago'])
    
    tickets = TicketPOS.objects.filter(pedido__caja_sesion=sesion).select_related('pedido', 'pedido__cliente')
    for t in tickets:
        pago = t.pedido.pagos.filter(estado=Pago.ESTADO_APROBADO).first()
        metodo_label = pago.get_metodo_display() if pago else 'N/A'
        
        writer.writerow([
            t.numero_serie,
            t.pedido.cliente.nombre_completo,
            t.pedido.cliente.dni_ruc,
            t.pedido.get_canal_display(),
            t.fecha_emision.strftime('%d/%m/%Y %H:%M:%S'),
            f"{t.subtotal:.2f}",
            f"{t.igv:.2f}",
            f"{t.total:.2f}",
            metodo_label
        ])
        
    return response
