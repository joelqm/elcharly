"""Historial de precios de producto (ventas, lista Excel, costo)."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.pos.views import cajero_required


def _dec(val) -> Decimal | None:
    if val is None or val == '':
        return None
    try:
        return Decimal(str(val).replace(',', '.').strip())
    except (InvalidOperation, ValueError):
        return None


def _iso(dt):
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.astimezone(timezone.get_current_timezone()).isoformat()


@cajero_required
def hub_historial_precios(request):
    return render(request, 'pos/hub_historial_precios.html')


@cajero_required
@require_GET
def hub_historial_precios_buscar(request):
    from apps.tienda.models import Producto
    from apps.tienda.search import filtrar_productos
    from apps.tienda.precios import con_igv

    q = (request.GET.get('q') or '').strip()
    if len(q) < 2:
        return JsonResponse({'resultados': []})

    qs = filtrar_productos(Producto.objects.all(), q)[:20]
    resultados = []
    for p in qs:
        resultados.append({
            'id': p.id,
            'codigo': p.codigo_articulo,
            'nombre': p.nombre_publico if hasattr(p, 'nombre_publico') else p.nombre,
            'lista_sin_igv': float(p.precio_venta or 0),
            'lista_con_igv': float(con_igv(p.precio_venta)),
            'costo': float(p.precio_costo or 0),
            'precio_web': float(p.precio_web) if p.precio_web is not None else None,
        })
    return JsonResponse({'resultados': resultados})


@cajero_required
@require_GET
def hub_historial_precios_datos(request, producto_id):
    from apps.pedidos.models import DetallePedido, Pedido
    from apps.tienda.models import LogCambioImportacion, Producto
    from apps.tienda.precios import con_igv

    producto = get_object_or_404(Producto, pk=producto_id)
    dias = int(request.GET.get('dias') or 365)
    dias = max(30, min(dias, 1825))
    desde = timezone.now() - timedelta(days=dias)

    # Ventas realizadas (precio con IGV al momento de la venta)
    ventas_qs = (
        DetallePedido.objects.filter(
            producto=producto,
            pedido__fecha_pedido__gte=desde,
        )
        .exclude(pedido__estado=Pedido.ESTADO_CANCELADO)
        .select_related('pedido')
        .order_by('pedido__fecha_pedido')
    )
    ventas = []
    for d in ventas_qs:
        ventas.append({
            't': _iso(d.pedido.fecha_pedido),
            'precio': float(d.precio_unitario),
            'cantidad': d.cantidad,
            'pedido': d.pedido.numero_pedido,
            'canal': d.pedido.canal,
            'estado': d.pedido.estado,
        })

    # Cambios de lista desde Excel (valores sin IGV → convertir a con IGV)
    logs = (
        LogCambioImportacion.objects.filter(
            codigo_articulo=producto.codigo_articulo,
            campo='precio_venta',
            tipo_cambio__in=[
                LogCambioImportacion.TIPO_PRECIO_SUBE,
                LogCambioImportacion.TIPO_PRECIO_BAJA,
            ],
            importacion__fecha__gte=desde,
        )
        .select_related('importacion')
        .order_by('importacion__fecha', 'id')
    )
    lista_import = []
    for log in logs:
        antes = _dec(log.valor_anterior)
        nuevo = _dec(log.valor_nuevo)
        if nuevo is None:
            continue
        lista_import.append({
            't': _iso(log.importacion.fecha),
            'precio': float(con_igv(nuevo)),
            'precio_sin_igv': float(nuevo),
            'antes': float(con_igv(antes)) if antes is not None else None,
            'antes_sin_igv': float(antes) if antes is not None else None,
            'tipo': log.tipo_cambio,
            'importacion_id': log.importacion_id,
            'archivo': log.importacion.archivo_nombre,
        })

    ahora = timezone.now()
    lista_actual = con_igv(producto.precio_venta)
    costo = producto.precio_costo or Decimal('0')

    return JsonResponse({
        'producto': {
            'id': producto.id,
            'codigo': producto.codigo_articulo,
            'nombre': getattr(producto, 'nombre_publico', None) or producto.nombre,
            'lista_sin_igv': float(producto.precio_venta or 0),
            'lista_con_igv': float(lista_actual),
            'costo': float(costo),
            'precio_web': float(producto.precio_web) if producto.precio_web is not None else None,
        },
        'desde': _iso(desde),
        'hasta': _iso(ahora),
        'ventas': ventas,
        'lista_import': lista_import,
        'referencia': {
            't_inicio': _iso(desde),
            't_fin': _iso(ahora),
            'costo': float(costo),
            'lista_actual': float(lista_actual),
            'precio_web': float(producto.precio_web) if producto.precio_web is not None else None,
        },
        'resumen': {
            'n_ventas': len(ventas),
            'n_cambios_lista': len(lista_import),
            'precio_venta_min': min((v['precio'] for v in ventas), default=None),
            'precio_venta_max': max((v['precio'] for v in ventas), default=None),
            'precio_venta_promedio': (
                round(sum(v['precio'] for v in ventas) / len(ventas), 2) if ventas else None
            ),
        },
    })
