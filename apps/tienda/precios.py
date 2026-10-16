"""
Convención de precios Makita (Excel «Lista de Productos» / Formato de Pedido).

- LISTA GENERAL (precio_venta) = precio de lista **sin IGV**.
- Precio sugerido de venta al público = lista × 1.18 (con IGV).
- precio_costo = compra (manual, no viene del Excel de lista).
- precio_web / precio_tachado = precios de tienda web (ya con IGV al público).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

TASA_IGV = Decimal('1.18')
MONEY_Q = Decimal('0.01')


def con_igv(precio_lista: Decimal | None) -> Decimal:
    """Lista sin IGV → precio sugerido con IGV (18 %)."""
    if precio_lista is None:
        return Decimal('0.00')
    return (Decimal(precio_lista) * TASA_IGV).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def sin_igv(precio_con_igv: Decimal | None) -> Decimal:
    """Precio con IGV → base neta (para desglose en ticket)."""
    if precio_con_igv is None:
        return Decimal('0.00')
    return (Decimal(precio_con_igv) / TASA_IGV).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


ETIQUETA_VS_LISTA = {
    'sobre': 'Sobre lista',
    'bajo': 'Bajo lista',
    'igual': 'Igual a lista',
    'sin_lista': 'Sin lista',
}


def comparar_vs_lista(precio_vendido, lista_sin_igv, cantidad=1) -> dict:
    """Vendido con IGV menos lista Makita con IGV (lista × 1.18).

    Positivo: se cobró por encima de la lista. Negativo: por debajo.
    """
    qty = int(cantidad or 0)
    vendido = Decimal(str(precio_vendido or 0)).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
    lista_base = Decimal(str(lista_sin_igv or 0))
    if lista_base <= 0 or qty <= 0:
        return {
            'lista_con_igv': None,
            'lista_linea': None,
            'vendido_linea': (vendido * Decimal(qty)).quantize(MONEY_Q) if qty > 0 else Decimal('0.00'),
            'diferencia': None,
            'estado': 'sin_lista',
            'etiqueta': ETIQUETA_VS_LISTA['sin_lista'],
        }
    lista = con_igv(lista_base)
    vendido_linea = (vendido * Decimal(qty)).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
    lista_linea = (lista * Decimal(qty)).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
    diferencia = (vendido_linea - lista_linea).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
    if diferencia > 0:
        estado = 'sobre'
    elif diferencia < 0:
        estado = 'bajo'
    else:
        estado = 'igual'
    return {
        'lista_con_igv': lista,
        'lista_linea': lista_linea,
        'vendido_linea': vendido_linea,
        'diferencia': diferencia,
        'estado': estado,
        'etiqueta': ETIQUETA_VS_LISTA[estado],
    }


def resumir_vs_lista(comparaciones: list[dict]) -> dict:
    """Suma líneas que sí tienen lista. Las demás quedan aparte."""
    vendido = Decimal('0.00')
    lista = Decimal('0.00')
    diferencia = Decimal('0.00')
    con_lista = 0
    sin_lista = 0
    for row in comparaciones:
        if row.get('estado') == 'sin_lista' or row.get('diferencia') is None:
            sin_lista += 1
            continue
        con_lista += 1
        vendido += Decimal(row['vendido_linea'])
        lista += Decimal(row['lista_linea'])
        diferencia += Decimal(row['diferencia'])
    diferencia = diferencia.quantize(MONEY_Q)
    if con_lista == 0:
        estado = 'sin_lista'
    elif diferencia > 0:
        estado = 'sobre'
    elif diferencia < 0:
        estado = 'bajo'
    else:
        estado = 'igual'
    return {
        'vendido': vendido.quantize(MONEY_Q),
        'lista': lista.quantize(MONEY_Q),
        'diferencia': diferencia,
        'con_lista': con_lista,
        'sin_lista': sin_lista,
        'estado': estado,
        'etiqueta': ETIQUETA_VS_LISTA[estado],
    }
