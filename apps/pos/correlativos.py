"""
Correlativos de comprobantes al estilo SUNAT (CPE).

Estructura oficial (boleta/factura electrónica):
  serie (4 caracteres) + '-' + correlativo (hasta 8 dígitos)
  - Boleta:  B001-00000001  (serie inicia en B)
  - Factura: F001-00000001  (serie inicia en F)

Recibo/ticket interno (NO es CPE SUNAT; uso interno de tienda):
  - R001-00000001

Referencia: FAQ CPE SUNAT — serie alfanumérica 4 posiciones + correlativo hasta 8.
"""
from __future__ import annotations

import re

# Serie fija por tipo (puedes abrir R002/B002 más adelante si necesitas otra caja/sede).
SERIE_RECIBO = 'R001'
SERIE_BOLETA = 'B001'
SERIE_FACTURA = 'F001'

_CORRELATIVO_RE = re.compile(r'^([A-Z0-9]{4})-(\d{1,8})$', re.I)


def serie_para_tipo(tipo_comprobante: str) -> str:
    tipo = (tipo_comprobante or '').lower()
    if tipo == 'boleta':
        return SERIE_BOLETA
    if tipo == 'factura':
        return SERIE_FACTURA
    return SERIE_RECIBO


def formatear_numero(serie: str, correlativo: int) -> str:
    return f'{serie.upper()}-{int(correlativo):08d}'


def _max_correlativo_en_qs(valores) -> int:
    max_n = 0
    for raw in valores:
        if not raw:
            continue
        m = _CORRELATIVO_RE.match(str(raw).strip())
        if not m:
            continue
        max_n = max(max_n, int(m.group(2)))
    return max_n


def siguiente_numero(serie: str) -> str:
    """
    Siguiente correlativo para la serie (R001 / B001 / F001).
    Mira tickets y pedidos POS para no chocar si comparten el mismo número visible.
    """
    from apps.pedidos.models import Pedido
    from apps.pos.models import TicketPOS

    serie = (serie or SERIE_RECIBO).upper()
    prefijo = f'{serie}-'

    tickets = TicketPOS.objects.filter(numero_serie__startswith=prefijo).values_list(
        'numero_serie', flat=True,
    )
    pedidos = Pedido.objects.filter(numero_pedido__startswith=prefijo).values_list(
        'numero_pedido', flat=True,
    )
    # También legado T-YYYY / VTA-YYYY por si se migran a mano (no mezclar en serie nueva).
    siguiente = max(_max_correlativo_en_qs(tickets), _max_correlativo_en_qs(pedidos)) + 1
    return formatear_numero(serie, siguiente)
