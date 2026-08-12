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
