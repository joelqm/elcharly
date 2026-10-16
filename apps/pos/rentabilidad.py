"""Series de ventas y diferencia contra la lista Makita con IGV.

La venta no guarda la lista del día. Se usa la lista actual del catálogo
(precio sin IGV × 1.18). Solo ventas concretadas de tienda y web.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.pedidos.models import DetallePedido, Pedido
from apps.tienda.precios import comparar_vs_lista

RANGOS = {
    'semana': 'Últimos 7 días',
    'mes': 'Este mes',
    'tres': 'Últimos 3 meses',
}


def _rango(codigo: str, hoy):
    if codigo == 'mes':
        return hoy.replace(day=1), 'dia', RANGOS['mes']
    if codigo == 'tres':
        return hoy - timedelta(days=89), 'semana', RANGOS['tres']
    return hoy - timedelta(days=6), 'dia', RANGOS['semana']


def _lunes(dia):
    return dia - timedelta(days=dia.weekday())


def _clave(dia, modo):
    if modo == 'semana':
        lunes = _lunes(dia)
        return lunes
    return dia


def _etiqueta(dia, modo):
    if modo == 'semana':
        return f"Sem {_lunes(dia).strftime('%d/%m')}"
    return dia.strftime('%d/%m')


def serie_ventas(rango: str = 'semana') -> dict:
    codigo = rango if rango in RANGOS else 'semana'
    hoy = timezone.localdate()
    inicio, modo, titulo = _rango(codigo, hoy)

    pedidos = Pedido.objects.filter(
        canal__in=(Pedido.CANAL_POS, Pedido.CANAL_WEB),
        estado__in=Pedido.ESTADOS_CONCRETADOS,
        fecha_pedido__date__gte=inicio,
        fecha_pedido__date__lte=hoy,
    )
    diff_por_clave = defaultdict(lambda: Decimal('0.00'))
    vendido_por_clave = defaultdict(lambda: Decimal('0.00'))
    referencia_por_clave = defaultdict(lambda: Decimal('0.00'))
    vendido_lista = Decimal('0.00')
    lista_total = Decimal('0.00')
    referencia_total = Decimal('0.00')
    sin_lista = 0
    from apps.pos.models import AjusteComercial
    pct = AjusteComercial.porcentaje()
    lineas = DetallePedido.objects.filter(pedido__in=pedidos).select_related('producto', 'pedido')
    for linea in lineas:
        lista_sin = linea.producto.precio_venta if linea.producto_id else 0
        comp = comparar_vs_lista(linea.precio_unitario, lista_sin, linea.cantidad, pct)
        if comp['diferencia'] is None:
            sin_lista += 1
            continue
        dia = timezone.localtime(linea.pedido.fecha_pedido).date()
        clave = _clave(dia, modo)
        diff_por_clave[clave] += comp['diferencia']
        vendido_por_clave[clave] += comp['vendido_linea']
        referencia_por_clave[clave] += comp['referencia_linea']
        vendido_lista += comp['vendido_linea']
        lista_total += comp['lista_linea']
        referencia_total += comp['referencia_linea']

    if modo == 'semana':
        cursor = _lunes(inicio)
        fin = _lunes(hoy)
        paso = timedelta(days=7)
    else:
        cursor = inicio
        fin = hoy
        paso = timedelta(days=1)

    labels = []
    vendido_serie = []
    referencia_serie = []
    diferencia = []
    while cursor <= fin:
        labels.append(_etiqueta(cursor, modo))
        vendido_serie.append(float(vendido_por_clave.get(cursor, Decimal('0.00'))))
        referencia_serie.append(float(referencia_por_clave.get(cursor, Decimal('0.00'))))
        diferencia.append(float(diff_por_clave.get(cursor, Decimal('0.00'))))
        cursor += paso

    diferencia_total = (vendido_lista - referencia_total).quantize(Decimal('0.01'))
    if lista_total <= 0 and vendido_lista <= 0:
        estado = 'sin_lista'
        etiqueta = 'Sin lista'
    elif diferencia_total > 0:
        estado = 'sobre'
        etiqueta = 'Con ganancia' if pct > 0 else 'Sobre lista'
    elif diferencia_total < 0:
        estado = 'bajo'
        etiqueta = 'Sin ganancia' if pct > 0 else 'Bajo lista'
    else:
        estado = 'igual'
        etiqueta = 'En el precio' if pct > 0 else 'Igual a lista'

    total_vendido = sum((Decimal(pedido.total or 0) for pedido in pedidos), Decimal('0.00'))
    return {
        'codigo': codigo,
        'titulo': titulo,
        'tipo': 'bar' if modo == 'dia' and codigo == 'semana' else 'line',
        'labels': labels,
        'ventas': vendido_serie,
        'referencia_serie': referencia_serie,
        'diferencia': diferencia,
        'total_vendido': total_vendido.quantize(Decimal('0.01')),
        'vendido_con_lista': vendido_lista.quantize(Decimal('0.01')),
        'lista': lista_total.quantize(Decimal('0.01')),
        'referencia': referencia_total.quantize(Decimal('0.01')),
        'diferencia_total': diferencia_total,
        'etiqueta': etiqueta,
        'estado': estado,
        'sin_lista': sin_lista,
        'descuento_pct': pct,
        'n_ventas': pedidos.count(),
    }
