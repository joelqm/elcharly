"""Lógica compartida de cotizaciones (crear/editar líneas)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from apps.tienda.models import Producto

from .models import Cotizacion, DetalleCotizacion


def parse_items_json(items):
    """Valida y normaliza ítems del builder. Devuelve (lista, error_msg)."""
    if not items:
        return [], 'Agrega al menos un producto a la cotización.'
    cleaned = []
    for raw in items:
        try:
            qty_raw = raw.get('cantidad')
            qty = int(qty_raw) if qty_raw is not None and str(qty_raw).strip() != '' else 1
            if qty < 0:
                continue
            precio = Decimal(str(raw.get('precio') or '0'))
            lista = Decimal(str(raw.get('precio_lista') or '0'))
            costo = Decimal(str(raw.get('precio_costo') or '0'))
        except (InvalidOperation, TypeError, ValueError):
            continue

        prod = None
        pid = raw.get('product_id')
        if pid:
            prod = Producto.objects.filter(id=pid).first()

        codigo = (raw.get('codigo') or (prod.codigo_articulo if prod else '') or '')[:50]
        desc = (raw.get('descripcion') or (prod.nombre if prod else '') or '')[:255]
        if prod and prod.posicion_despiece:
            pos_str = str(prod.posicion_despiece).strip()
            if pos_str:
                if not pos_str.casefold().startswith('pos'):
                    pos_str = f"Pos. {pos_str}"
                if pos_str not in desc:
                    desc = f"{desc} ({pos_str})"[:255]
        if not desc:
            continue

        cleaned.append({
            'repuesto': prod,
            'codigo_articulo': codigo,
            'descripcion': desc,
            'cantidad': qty,
            'precio_unitario': precio,
            'precio_lista': lista,
            'precio_costo': costo,
        })
    if not cleaned:
        return [], 'No se pudo guardar ningún ítem válido.'
    return cleaned, None


def reemplazar_detalles(cotizacion: Cotizacion, items_clean: list):
    """Reemplaza líneas sin borrar la cabecera (correlativo se conserva)."""
    cotizacion.detalles.all().delete()
    for item in items_clean:
        DetalleCotizacion.objects.create(
            cotizacion=cotizacion,
            repuesto=item['repuesto'],
            codigo_articulo=item['codigo_articulo'],
            descripcion=item['descripcion'],
            descripcion_manual=item['descripcion'] if not item['repuesto'] else None,
            cantidad=item['cantidad'],
            precio_unitario=item['precio_unitario'],
            precio_lista=item['precio_lista'],
            precio_costo=item['precio_costo'],
        )
    cotizacion.calcular_totales()
