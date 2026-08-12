from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from decimal import Decimal
import datetime
import json

from .models import Cotizacion
from .services import parse_items_json, reemplazar_detalles
from apps.clientes.models import Cliente
from apps.tienda.models import Producto
from apps.pedidos.models import Pedido, DetallePedido


def quote_staff_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        from apps.sistema.internal_access import (
            is_staff_interno,
            ocultar_sistema_interno,
            redirect_pos_login,
        )

        if not request.user.is_authenticated:
            return redirect_pos_login(request)
        if not is_staff_interno(request.user):
            return ocultar_sistema_interno(request)
        allowed_roles = [request.user.ROLE_ADMIN, request.user.ROLE_VENDEDOR, request.user.ROLE_TECNICO]
        if request.user.rol not in allowed_roles and not request.user.is_superuser:
            return ocultar_sistema_interno(request)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def _parse_cliente_y_cabecera(request):
    from django.conf import settings
    from .models import observaciones_default

    cliente_id = request.POST.get('cliente')
    nombre_temp = request.POST.get('nombre_cliente_temporal', '').strip()
    dni_temp = request.POST.get('dni_ruc_cliente_temporal', '').strip()
    correo_temp = request.POST.get('correo_cliente_temporal', '').strip()
    telefono_temp = request.POST.get('telefono_cliente_temporal', '').strip()
    direccion_temp = request.POST.get('direccion_cliente_temporal', '').strip()
    notas = request.POST.get('notas', '').strip()

    obs_raw = request.POST.get('observaciones_json', '').strip()
    observaciones = []
    if obs_raw:
        try:
            parsed = json.loads(obs_raw)
            if isinstance(parsed, list):
                observaciones = [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            observaciones = []
    if not observaciones:
        negocio = getattr(settings, 'NEGOCIO', {}) or {}
        observaciones = observaciones_default(negocio.get('whatsapp_display'))

    cliente = None
    if cliente_id:
        cliente = get_object_or_404(Cliente, id=cliente_id)
    elif not nombre_temp or not dni_temp:
        return None, 'Selecciona un cliente del CRM o ingresa nombre y RUC/DNI manual.'

    data = {
        'cliente': cliente,
        'nombre_cliente_temporal': nombre_temp if not cliente else None,
        'dni_ruc_cliente_temporal': dni_temp if not cliente else None,
        'correo_cliente_temporal': correo_temp if not cliente else None,
        'telefono_cliente_temporal': telefono_temp if not cliente else None,
        'direccion_cliente_temporal': direccion_temp if not cliente else None,
        'observaciones': observaciones,
        'notas': notas or None,
    }
    return data, None


def _builder_context(cotizacion=None):
    from django.conf import settings
    from .models import observaciones_default

    negocio = getattr(settings, 'NEGOCIO', {}) or {}
    if cotizacion and cotizacion.observaciones:
        obs = [str(x) for x in cotizacion.observaciones if str(x).strip()]
    else:
        obs = observaciones_default(negocio.get('whatsapp_display'))

    ctx = {
        'buscar_url': '/pos/productos/buscar/',
        'cotizacion': cotizacion,
        'es_edicion': cotizacion is not None,
        'initial_lines_json': '[]',
        'observaciones_iniciales': obs,
        'observaciones_json': json.dumps(obs, ensure_ascii=False),
    }
    if cotizacion:
        lines = []
        for d in cotizacion.detalles.all().select_related('repuesto'):
            lines.append({
                'product_id': d.repuesto_id,
                'codigo': d.codigo_linea,
                'descripcion': d.descripcion_linea,
                'precio': float(d.precio_unitario or 0),
                'precio_lista': float(d.precio_lista or 0),
                'precio_costo': float(d.precio_costo or 0),
                'cantidad': d.cantidad,
            })
        ctx['initial_lines_json'] = json.dumps(lines, ensure_ascii=False)
    return ctx


@quote_staff_required
def cotizacion_lista(request):
    query = request.GET.get('q', '').strip()
    estado_filter = request.GET.get('estado', '').strip()
    cotizaciones = Cotizacion.objects.all().select_related('cliente', 'creado_por').order_by('-fecha_creacion')
    if query:
        cotizaciones = cotizaciones.filter(
            Q(numero__icontains=query)
            | Q(cliente__nombre_completo__icontains=query)
            | Q(nombre_cliente_temporal__icontains=query)
            | Q(modelo_equipo__icontains=query)
            | Q(dni_ruc_cliente_temporal__icontains=query)
        )
    if estado_filter:
        cotizaciones = cotizaciones.filter(estado=estado_filter)
    return render(request, 'cotizaciones/lista.html', {
        'cotizaciones': cotizaciones[:200],
        'query': query,
        'estado_filter': estado_filter,
        'estados': Cotizacion.ESTADO_CHOICES,
        'siguiente_correlativo': Cotizacion.siguiente_numero(),
    })


@quote_staff_required
def cotizacion_detalle(request, cotizacion_id):
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id)
    detalles = list(cotizacion.detalles.all().select_related('repuesto'))
    url_publica = cotizacion.obtener_url_publica(request=request)
    whatsapp_link = cotizacion.obtener_link_whatsapp(request=request)
    tiene_imagenes = any(d.imagen_url for d in detalles)
    return render(request, 'cotizaciones/detalle.html', {
        'cotizacion': cotizacion,
        'detalles': detalles,
        'url_publica': url_publica,
        'whatsapp_link': whatsapp_link,
        'tiene_imagenes': tiene_imagenes,
    })


@quote_staff_required
def cotizacion_nueva(request):
    if request.method == 'POST':
        cabecera, err = _parse_cliente_y_cabecera(request)
        if err:
            messages.error(request, err)
            return redirect('cotizaciones:nueva')

        try:
            items = json.loads(request.POST.get('items_json', '').strip() or '[]')
        except json.JSONDecodeError:
            messages.error(request, 'No se pudieron leer los ítems de la cotización.')
            return redirect('cotizaciones:nueva')

        items_clean, err = parse_items_json(items)
        if err:
            messages.error(request, err)
            return redirect('cotizaciones:nueva')

        cotizacion = Cotizacion.objects.create(
            **cabecera,
            estado=Cotizacion.ESTADO_BORRADOR,
            creado_por=request.user,
        )
        reemplazar_detalles(cotizacion, items_clean)
        messages.success(request, f'Cotización {cotizacion.numero} creada.')
        return redirect('cotizaciones:detalle', cotizacion_id=cotizacion.id)

    return render(request, 'cotizaciones/crear.html', _builder_context())


@quote_staff_required
def cotizacion_editar(request, cotizacion_id):
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id)
    if not cotizacion.puede_editar:
        messages.error(
            request,
            f'No se puede editar una cotización en estado «{cotizacion.get_estado_display()}».',
        )
        return redirect('cotizaciones:detalle', cotizacion_id=cotizacion.id)

    if request.method == 'POST':
        cabecera, err = _parse_cliente_y_cabecera(request)
        if err:
            messages.error(request, err)
            return redirect('cotizaciones:editar', cotizacion_id=cotizacion.id)

        try:
            items = json.loads(request.POST.get('items_json', '').strip() or '[]')
        except json.JSONDecodeError:
            messages.error(request, 'No se pudieron leer los ítems de la cotización.')
            return redirect('cotizaciones:editar', cotizacion_id=cotizacion.id)

        items_clean, err = parse_items_json(items)
        if err:
            messages.error(request, err)
            return redirect('cotizaciones:editar', cotizacion_id=cotizacion.id)

        for key, val in cabecera.items():
            setattr(cotizacion, key, val)
        # Conserva número (correlativo) y estado actual
        cotizacion.save()
        reemplazar_detalles(cotizacion, items_clean)
        messages.success(request, f'Cotización {cotizacion.numero} actualizada.')
        return redirect('cotizaciones:detalle', cotizacion_id=cotizacion.id)

    return render(request, 'cotizaciones/crear.html', _builder_context(cotizacion))


@quote_staff_required
def anular_cotizacion(request, cotizacion_id):
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id)
    if request.method != 'POST':
        return redirect('cotizaciones:detalle', cotizacion_id=cotizacion.id)

    if not cotizacion.puede_anular:
        messages.error(
            request,
            f'No se puede anular una cotización en estado «{cotizacion.get_estado_display()}».',
        )
        return redirect('cotizaciones:detalle', cotizacion_id=cotizacion.id)

    motivo = (request.POST.get('motivo') or '').strip()
    nota = f'[ANULADA {datetime.date.today().isoformat()}]'
    if motivo:
        nota += f' {motivo}'
    prev = (cotizacion.notas or '').strip()
    cotizacion.notas = f'{nota}\n{prev}'.strip() if prev else nota
    cotizacion.estado = Cotizacion.ESTADO_ANULADA
    cotizacion.save(update_fields=['estado', 'notas'])
    messages.success(request, f'Cotización {cotizacion.numero} anulada (el correlativo se conserva).')
    return redirect('cotizaciones:lista')


@quote_staff_required
def buscar_clientes(request):
    q = (request.GET.get('q') or '').strip()
    qs = Cliente.objects.all().order_by('nombre_completo')
    if q:
        qs = qs.filter(
            Q(nombre_completo__icontains=q)
            | Q(dni_ruc__icontains=q)
            | Q(telefono__icontains=q)
        )
    data = [
        {
            'id': c.id,
            'nombre': c.nombre_completo,
            'dni_ruc': c.dni_ruc,
            'telefono': c.telefono or '',
            'direccion': c.direccion or '',
            'correo': c.correo or '',
        }
        for c in qs[:20]
    ]
    return JsonResponse({'clientes': data})


@quote_staff_required
def aprobar_cotizacion(request, cotizacion_id):
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id)
    if cotizacion.estado == Cotizacion.ESTADO_APROBADA:
        messages.error(request, 'Esta cotización ya fue aprobada.')
        return redirect('cotizaciones:detalle', cotizacion_id=cotizacion.id)
    if cotizacion.estado == Cotizacion.ESTADO_ANULADA:
        messages.error(request, 'No se puede aprobar una cotización anulada.')
        return redirect('cotizaciones:detalle', cotizacion_id=cotizacion.id)

    if request.method != 'POST':
        return redirect('cotizaciones:detalle', cotizacion_id=cotizacion.id)

    cliente = cotizacion.cliente
    if not cliente:
        try:
            cliente = Cliente.objects.filter(dni_ruc=cotizacion.dni_ruc_cliente_temporal).first()
            if not cliente:
                cliente = Cliente.objects.create(
                    nombre_completo=cotizacion.nombre_cliente_temporal,
                    dni_ruc=cotizacion.dni_ruc_cliente_temporal,
                    telefono=cotizacion.telefono_cliente_temporal,
                    correo=cotizacion.correo_cliente_temporal,
                    direccion=cotizacion.direccion_cliente_temporal,
                    canal_origen=Cliente.CANAL_REFERIDO,
                    etiqueta=Cliente.ETIQUETA_NUEVO,
                    notas=f'Registrado al aprobar cotización {cotizacion.numero}',
                )
        except Exception as exc:
            messages.error(request, f'Error al registrar cliente: {exc}')
            return redirect('cotizaciones:detalle', cotizacion_id=cotizacion.id)

    repuesto_manual_prod, _ = Producto.objects.get_or_create(
        codigo_articulo='REP-MANUAL',
        defaults={
            'nombre': 'Repuesto no catalogado de Cotización',
            'slug': 'repuesto-manual-cotizacion',
            'precio_venta': Decimal('0.00'),
            'stock': 9999,
            'tipo': Producto.TIPO_REPUESTO,
            'familia_sap': 'REPUESTOS',
        },
    )

    pedido = Pedido.objects.create(
        cliente=cliente,
        canal=Pedido.CANAL_COTIZACION,
        estado=Pedido.ESTADO_PENDIENTE,
        subtotal=cotizacion.subtotal,
        igv=cotizacion.igv,
        total=cotizacion.total,
        atendido_por=request.user,
        notas=f'Pedido generado desde cotización {cotizacion.numero}. ' + (cotizacion.notas or ''),
    )

    for item in cotizacion.detalles.all():
        prod = item.repuesto or repuesto_manual_prod
        DetallePedido.objects.create(
            pedido=pedido,
            producto=prod,
            codigo_articulo=item.codigo_linea or prod.codigo_articulo,
            nombre_producto=item.descripcion_linea[:255],
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            subtotal=item.subtotal,
        )

    cotizacion.estado = Cotizacion.ESTADO_APROBADA
    cotizacion.save(update_fields=['estado'])
    messages.success(request, f'Cotización aprobada. Pedido {pedido.numero_pedido} generado.')
    return redirect('cotizaciones:detalle', cotizacion_id=cotizacion.id)


@quote_staff_required
def generar_pdf(request, cotizacion_id):
    from apps.cotizaciones.exporters.pdf_cotizacion import exportar_cotizacion_pdf

    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id)
    pdf = exportar_cotizacion_pdf(cotizacion)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="cotizacion_{cotizacion.numero}.pdf"'
    return response


@quote_staff_required
def generar_excel(request, cotizacion_id):
    from apps.cotizaciones.exporters.excel_cotizacion import exportar_cotizacion_excel

    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id)
    data = exportar_cotizacion_excel(cotizacion)
    response = HttpResponse(
        data,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="cotizacion_{cotizacion.numero}.xlsx"'
    return response


def cotizacion_publica_ver(request, token):
    return cotizacion_publica_pdf(request, token)


def cotizacion_publica_pdf(request, token):
    from apps.cotizaciones.exporters.pdf_cotizacion import exportar_cotizacion_pdf

    cotizacion = get_object_or_404(Cotizacion, token_publico=token)
    pdf = exportar_cotizacion_pdf(cotizacion)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="cotizacion_{cotizacion.numero}.pdf"'
    return response


