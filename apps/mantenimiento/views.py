from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.db.models import F, Q
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponse
from django.contrib import messages
from datetime import timedelta, datetime
from decimal import Decimal, InvalidOperation
import logging

from .models import EquipoRegistrado, Mantenimiento, OrdenTrabajoLinea
from apps.clientes.models import Cliente
from apps.tienda.models import Producto
from apps.inventario.models import MovimientoInventario
from apps.pedidos.models import Pedido
from proyecto_makita.email_utils import enviar_alerta_retiro

logger = logging.getLogger(__name__)


def tecnico_required(view_func):
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
        roles_ok = [
            request.user.ROLE_TECNICO,
            request.user.ROLE_ADMIN,
            request.user.ROLE_VENDEDOR,
        ]
        if request.user.rol not in roles_ok and not request.user.is_superuser:
            return ocultar_sistema_interno(request)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def _parse_date(raw):
    raw = (raw or '').strip()
    if not raw:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _guardar_lineas(mantenimiento, request):
    codigos = request.POST.getlist('linea_codigo')
    descs = request.POST.getlist('linea_descripcion')
    cants = request.POST.getlist('linea_cantidad')
    mantenimiento.lineas.all().delete()
    orden = 0
    for codigo, desc, cant in zip(codigos, descs, cants):
        codigo = (codigo or '').strip()[:50]
        if not codigo:
            continue
        try:
            cantidad = max(1, int(cant or 1))
        except (TypeError, ValueError):
            cantidad = 1
        OrdenTrabajoLinea.objects.create(
            mantenimiento=mantenimiento,
            codigo=codigo,
            descripcion=(desc or '').strip()[:255],
            cantidad=cantidad,
            orden=orden,
        )
        orden += 1


@tecnico_required
def tecnico_dashboard(request):
    ordenes_activas = Mantenimiento.objects.filter(
        estado__in=[Mantenimiento.ESTADO_INGRESADO, Mantenimiento.ESTADO_PROCESO]
    ).select_related('equipo', 'tecnico', 'equipo__cliente', 'equipo__producto')

    ordenes_listas = Mantenimiento.objects.filter(
        estado=Mantenimiento.ESTADO_LISTO
    ).select_related('equipo', 'tecnico', 'equipo__cliente')

    ordenes_entregadas = Mantenimiento.objects.filter(
        estado=Mantenimiento.ESTADO_ENTREGADO
    ).select_related('equipo', 'tecnico', 'equipo__cliente')[:25]

    equipos_alerta = EquipoRegistrado.objects.filter(
        horas_uso_actuales__gte=F('horas_proximo_mantenimiento'),
        estado=EquipoRegistrado.ESTADO_ACTIVO,
    ).select_related('cliente', 'producto')

    sla_dias = getattr(settings, 'MANTENIMIENTO_SLA_DIAS', 5)
    limite_sla = timezone.now() - timedelta(days=sla_dias)
    ordenes_sla = Mantenimiento.objects.filter(
        estado__in=[Mantenimiento.ESTADO_INGRESADO, Mantenimiento.ESTADO_PROCESO],
        fecha_ingreso__lte=limite_sla,
    ).select_related('equipo', 'equipo__cliente', 'tecnico')

    q = request.GET.get('q', '').strip()
    resultados = []
    if q:
        resultados = _buscar_equipos(q)[:40]

    context = {
        'ordenes_activas': ordenes_activas,
        'ordenes_listas': ordenes_listas,
        'ordenes_entregadas': ordenes_entregadas,
        'equipos_alerta': equipos_alerta,
        'ordenes_sla': ordenes_sla,
        'sla_dias': sla_dias,
        'search_query': q,
        'resultados': resultados,
    }
    return render(request, 'mantenimiento/dashboard.html', context)


def _buscar_equipos(q: str):
    """Busca equipos / clientes / pedidos / boletas para historial clínico."""
    qs = EquipoRegistrado.objects.select_related(
        'cliente', 'producto', 'pedido_origin'
    ).prefetch_related('mantenimientos')

    filtros = (
        Q(numero_serie__icontains=q)
        | Q(modelo_alternativo__icontains=q)
        | Q(producto__nombre__icontains=q)
        | Q(producto__modelo__icontains=q)
        | Q(producto__codigo_articulo__icontains=q)
        | Q(cliente__nombre_completo__icontains=q)
        | Q(cliente__dni_ruc__icontains=q)
        | Q(cliente__telefono__icontains=q)
        | Q(boleta_factura__icontains=q)
        | Q(pedido_origin__numero_pedido__icontains=q)
        | Q(mantenimientos__numero_ot__icontains=q)
        | Q(mantenimientos__boleta_factura__icontains=q)
    )
    # Ticket POS / comprobante
    try:
        from apps.pos.models import TicketPOS
        ticket_ids = TicketPOS.objects.filter(
            Q(numero_serie__icontains=q) | Q(pedido__numero_pedido__icontains=q)
        ).values_list('pedido_id', flat=True)[:50]
        if ticket_ids:
            filtros |= Q(pedido_origin_id__in=ticket_ids)
    except Exception:
        pass

    return qs.filter(filtros).distinct().order_by('-fecha_registro')


@tecnico_required
def buscar_historial(request):
    q = request.GET.get('q', '').strip()
    resultados = _buscar_equipos(q)[:50] if q else []
    return render(request, 'mantenimiento/buscar.html', {
        'q': q,
        'resultados': resultados,
    })


@tecnico_required
def registrar_ingreso(request):
    """Compat: redirige al flujo nuevo de crear OT."""
    return redirect('mantenimiento:nueva_ot')


@tecnico_required
def nueva_ot(request):
    """Alta de OT: equipo nuestro (buscar) o externo + formulario."""
    clientes = Cliente.objects.all().order_by('nombre_completo')
    productos = Producto.objects.filter(
        Q(tipo=Producto.TIPO_HERRAMIENTA) | Q(familia_sap='EQUIPOS')
    ).order_by('nombre')

    equipo_id = request.GET.get('equipo') or request.POST.get('equipo_id')
    equipo_pre = None
    if equipo_id:
        equipo_pre = EquipoRegistrado.objects.filter(pk=equipo_id).select_related(
            'cliente', 'producto'
        ).first()

    if request.method == 'POST':
        tipo = request.POST.get('tipo', Mantenimiento.TIPO_CORRECTIVO)
        if tipo not in dict(Mantenimiento.TIPO_CHOICES):
            tipo = Mantenimiento.TIPO_CORRECTIVO

        origen = request.POST.get('origen', EquipoRegistrado.ORIGEN_NUESTRO)
        equipo = equipo_pre

        if not equipo:
            numero_serie = (request.POST.get('numero_serie') or '').strip().upper()
            if not numero_serie:
                messages.error(request, 'Indica el número de serie del equipo.')
                return redirect('mantenimiento:nueva_ot')

            equipo = EquipoRegistrado.objects.filter(numero_serie__iexact=numero_serie).first()
            cliente_id = request.POST.get('cliente')
            producto_id = request.POST.get('producto')
            modelo_alt = (request.POST.get('modelo_alternativo') or '').strip()

            if origen == EquipoRegistrado.ORIGEN_EXTERNO or not equipo:
                if not cliente_id:
                    # Crear cliente rápido
                    dni = (request.POST.get('cliente_dni') or '').strip()
                    nombre = (request.POST.get('cliente_nombre') or '').strip()
                    if not nombre:
                        messages.error(request, 'Nombre del cliente obligatorio para equipo nuevo.')
                        return redirect('mantenimiento:nueva_ot')
                    cliente, _ = Cliente.objects.get_or_create(
                        dni_ruc=dni or f'TMP-{timezone.now().strftime("%Y%m%d%H%M%S")}',
                        defaults={
                            'nombre_completo': nombre,
                            'telefono': (request.POST.get('cliente_telefono') or '').strip(),
                            'tipo': 'persona',
                            'canal_origen': 'pos',
                        },
                    )
                    if dni and cliente.nombre_completo != nombre:
                        cliente.nombre_completo = nombre
                        cliente.telefono = (request.POST.get('cliente_telefono') or cliente.telefono or '')
                        cliente.save()
                else:
                    cliente = get_object_or_404(Cliente, pk=cliente_id)

                producto = Producto.objects.filter(pk=producto_id).first() if producto_id else None
                if not equipo:
                    equipo = EquipoRegistrado.objects.create(
                        cliente=cliente,
                        producto=producto,
                        modelo_alternativo=modelo_alt if not producto else None,
                        numero_serie=numero_serie,
                        origen=origen if origen in dict(EquipoRegistrado.ORIGEN_CHOICES) else EquipoRegistrado.ORIGEN_EXTERNO,
                        distribuidor=(request.POST.get('distribuidor') or '').strip(),
                        boleta_factura=(request.POST.get('boleta_factura') or '').strip(),
                        fecha_compra=_parse_date(request.POST.get('fecha_compra')),
                        estado=EquipoRegistrado.ESTADO_MANTENIMIENTO,
                    )
                else:
                    equipo.cliente = cliente
                    equipo.origen = origen
                    equipo.estado = EquipoRegistrado.ESTADO_MANTENIMIENTO
                    equipo.save()
            else:
                equipo.estado = EquipoRegistrado.ESTADO_MANTENIMIENTO
                equipo.save(update_fields=['estado'])

        ot = Mantenimiento(
            equipo=equipo,
            tipo=tipo,
            tecnico=request.user,
            diagnostico=(request.POST.get('diagnostico') or '').strip(),
            causa=(request.POST.get('causa') or '').strip(),
            informe_tecnico=(request.POST.get('informe_tecnico') or '').strip(),
            accesorios=(request.POST.get('accesorios') or '').strip(),
            observaciones=(request.POST.get('observaciones') or '').strip() or None,
            boleta_factura=(request.POST.get('boleta_factura') or equipo.boleta_factura or '').strip(),
            distribuidor=(request.POST.get('distribuidor') or equipo.distribuidor or '').strip(),
            atencion_sr=(request.POST.get('atencion_sr') or '').strip(),
            fecha_recepcion=_parse_date(request.POST.get('fecha_recepcion')) or timezone.localdate(),
            fecha_compra=_parse_date(request.POST.get('fecha_compra')) or equipo.fecha_compra,
            estado=Mantenimiento.ESTADO_INGRESADO,
        )
        if tipo == Mantenimiento.TIPO_GARANTIA:
            ot.estado_garantia = Mantenimiento.GARANTIA_BORRADOR
        ot.save()
        _guardar_lineas(ot, request)
        messages.success(request, f'Se creó {ot.numero_ot}.')
        return redirect('mantenimiento:editar_ot', mantenimiento_id=ot.id)

    return render(request, 'mantenimiento/ot_form.html', {
        'clientes': clientes,
        'productos': productos,
        'equipo': equipo_pre,
        'ot': None,
        'lineas': [],
        'modo': 'crear',
        'tipos': Mantenimiento.TIPO_CHOICES,
    })


@tecnico_required
def editar_ot(request, mantenimiento_id):
    ot = get_object_or_404(
        Mantenimiento.objects.select_related(
            'equipo', 'equipo__cliente', 'equipo__producto', 'tecnico'
        ).prefetch_related('lineas'),
        pk=mantenimiento_id,
    )
    equipo = ot.equipo

    if request.method == 'POST':
        accion = request.POST.get('accion', 'guardar')

        if accion == 'export_ot':
            from apps.mantenimiento.exporters.excel_ot import exportar_ot_excel, filename_ot
            data = exportar_ot_excel(ot)
            resp = HttpResponse(
                data,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            resp['Content-Disposition'] = f'attachment; filename="{filename_ot(ot)}"'
            return resp

        if accion == 'export_garantia':
            from apps.mantenimiento.exporters.excel_ot import exportar_garantia_excel, filename_garantia
            data = exportar_garantia_excel(ot)
            resp = HttpResponse(
                data,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            resp['Content-Disposition'] = f'attachment; filename="{filename_garantia(ot)}"'
            return resp

        ot.tipo = request.POST.get('tipo', ot.tipo)
        ot.estado = request.POST.get('estado', ot.estado)
        ot.diagnostico = (request.POST.get('diagnostico') or '').strip()
        ot.causa = (request.POST.get('causa') or '').strip()
        ot.informe_tecnico = (request.POST.get('informe_tecnico') or '').strip()
        ot.accesorios = (request.POST.get('accesorios') or '').strip()
        ot.trabajos_realizados = (request.POST.get('trabajos_realizados') or '').strip()
        ot.observaciones = (request.POST.get('observaciones') or '').strip() or None
        ot.boleta_factura = (request.POST.get('boleta_factura') or '').strip()
        ot.distribuidor = (request.POST.get('distribuidor') or '').strip()
        ot.atencion_sr = (request.POST.get('atencion_sr') or '').strip()
        ot.fecha_recepcion = _parse_date(request.POST.get('fecha_recepcion')) or ot.fecha_recepcion
        ot.fecha_compra = _parse_date(request.POST.get('fecha_compra')) or ot.fecha_compra
        try:
            ot.costo_mano_obra = Decimal(request.POST.get('costo_mano_obra') or '0')
        except (InvalidOperation, ValueError):
            pass

        # Garantía Lima
        ot.estado_garantia = request.POST.get('estado_garantia', ot.estado_garantia)
        ot.autorizacion_mpe = (request.POST.get('autorizacion_mpe') or '').strip()
        ot.nombre_mpe = (request.POST.get('nombre_mpe') or '').strip()
        ot.comentario_mpe = (request.POST.get('comentario_mpe') or '').strip()
        ot.fecha_aprobacion_mpe = _parse_date(request.POST.get('fecha_aprobacion_mpe'))
        ot.categoria_falla = (request.POST.get('categoria_falla') or '').strip()
        try:
            raw_mo = (request.POST.get('mano_obra_mpe') or '').strip()
            ot.mano_obra_mpe = Decimal(raw_mo) if raw_mo else None
        except (InvalidOperation, ValueError):
            pass

        if ot.autorizacion_mpe and ot.estado_garantia == Mantenimiento.GARANTIA_BORRADOR:
            ot.estado_garantia = Mantenimiento.GARANTIA_APROBADO

        estado_anterior = Mantenimiento.objects.filter(pk=ot.pk).values_list('estado', flat=True).first()
        ot.save()
        _guardar_lineas(ot, request)

        # Sync boleta on equipo
        if ot.boleta_factura and not equipo.boleta_factura:
            equipo.boleta_factura = ot.boleta_factura
            equipo.save(update_fields=['boleta_factura'])

        if (
            ot.estado == Mantenimiento.ESTADO_LISTO
            and estado_anterior != Mantenimiento.ESTADO_LISTO
        ):
            try:
                enviar_alerta_retiro(ot)
            except Exception:
                logger.exception('No se pudo enviar alerta de retiro')

        messages.success(request, f'{ot.numero_ot} actualizada.')
        return redirect('mantenimiento:editar_ot', mantenimiento_id=ot.id)

    return render(request, 'mantenimiento/ot_form.html', {
        'ot': ot,
        'equipo': equipo,
        'lineas': list(ot.lineas.all()),
        'modo': 'editar',
        'tipos': Mantenimiento.TIPO_CHOICES,
        'estados': Mantenimiento.ESTADO_CHOICES,
        'estados_garantia': Mantenimiento.GARANTIA_CHOICES,
        'clientes': Cliente.objects.none(),
        'productos': Producto.objects.none(),
    })


def _sincronizar_inventario_repuestos(mantenimiento, nuevos_ids, usuario):
    anteriores = set(mantenimiento.repuestos_usados.values_list('id', flat=True))
    nuevos = set(int(i) for i in nuevos_ids if str(i).isdigit())
    agregados = nuevos - anteriores
    removidos = anteriores - nuevos

    for prod_id in agregados:
        producto = Producto.objects.filter(id=prod_id).first()
        if not producto:
            continue
        if producto.stock < 1:
            raise ValueError(f'Stock insuficiente del repuesto «{producto.nombre}».')
        MovimientoInventario.objects.create(
            producto=producto,
            tipo=MovimientoInventario.TIPO_SALIDA,
            cantidad=1,
            motivo=MovimientoInventario.MOTIVO_MANTENIMIENTO,
            usuario=usuario,
        )

    for prod_id in removidos:
        producto = Producto.objects.filter(id=prod_id).first()
        if not producto:
            continue
        MovimientoInventario.objects.create(
            producto=producto,
            tipo=MovimientoInventario.TIPO_ENTRADA,
            cantidad=1,
            motivo=MovimientoInventario.MOTIVO_MANTENIMIENTO,
            usuario=usuario,
        )


@tecnico_required
def editar_mantenimiento(request, mantenimiento_id):
    """Compat: redirige al editor OT unificado."""
    return redirect('mantenimiento:editar_ot', mantenimiento_id=mantenimiento_id)


@tecnico_required
def historial_equipo(request, equipo_id):
    equipo = get_object_or_404(
        EquipoRegistrado.objects.select_related('cliente', 'producto', 'pedido_origin'),
        id=equipo_id,
    )
    mantenimientos = equipo.mantenimientos.all().select_related('tecnico').prefetch_related('lineas')
    return render(request, 'mantenimiento/historial_equipo.html', {
        'equipo': equipo,
        'mantenimientos': mantenimientos,
    })
