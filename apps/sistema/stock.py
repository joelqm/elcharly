"""Helpers de stock por sede y pool web (fallback POS)."""
from __future__ import annotations


def stock_para_venta(producto, sede=None) -> int:
    """Stock disponible en POS: tienda (o sede) + web."""
    from apps.tienda.models import Producto
    if getattr(producto, 'tipo', None) == Producto.TIPO_SERVICIO:
        return 999999
    web = max(0, int(producto.stock_web or 0))
    if sede is None or sede.compartir_productos:
        return max(0, int(producto.stock or 0)) + web
    from apps.tienda.models import StockSede
    row, _ = StockSede.objects.get_or_create(
        producto=producto, sede=sede, defaults={'cantidad': 0},
    )
    return max(0, int(row.cantidad or 0)) + web


def descontar_stock_pos(producto, cantidad: int, sede=None, usuario=None):
    """Descuenta stock POS: primero tienda/sede, luego web automáticamente."""
    from django.db import transaction
    from apps.inventario.models import MovimientoInventario
    from apps.tienda.models import Producto

    if cantidad <= 0 or getattr(producto, 'tipo', None) == Producto.TIPO_SERVICIO:
        return

    with transaction.atomic():
        producto = (
            Producto.objects.select_for_update()
            .filter(pk=producto.pk)
            .first()
        )
        if not producto:
            raise ValueError('Producto no encontrado')

        disponible = stock_para_venta(producto, sede)
        if disponible < cantidad:
            raise ValueError(
                f'Stock insuficiente para {producto.nombre} '
                f'(disp. {disponible}, solicitado {cantidad})'
            )

        restante = cantidad

        if sede is not None and not sede.compartir_productos:
            from apps.tienda.models import StockSede
            row, _ = StockSede.objects.select_for_update().get_or_create(
                producto=producto, sede=sede, defaults={'cantidad': 0},
            )
            from_sede = min(row.cantidad, restante)
            if from_sede:
                row.cantidad -= from_sede
                row.save(update_fields=['cantidad'])
                mov = MovimientoInventario(
                    producto=producto,
                    tipo=MovimientoInventario.TIPO_SALIDA,
                    cantidad=from_sede,
                    motivo=MovimientoInventario.MOTIVO_VENTA_POS,
                    destino=MovimientoInventario.DESTINO_TIENDA,
                    usuario=usuario,
                )
                mov._skip_stock = True
                mov.save()
                restante -= from_sede
        else:
            from_tienda = min(max(0, producto.stock), restante)
            if from_tienda:
                MovimientoInventario.objects.create(
                    producto=producto,
                    tipo=MovimientoInventario.TIPO_SALIDA,
                    cantidad=from_tienda,
                    motivo=MovimientoInventario.MOTIVO_VENTA_POS,
                    destino=MovimientoInventario.DESTINO_TIENDA,
                    usuario=usuario,
                )
                restante -= from_tienda
                producto.refresh_from_db()

        if restante:
            if producto.stock_web < restante:
                raise ValueError(
                    f'Stock web insuficiente para {producto.nombre} '
                    f'(disp. web {producto.stock_web})'
                )
            MovimientoInventario.objects.create(
                producto=producto,
                tipo=MovimientoInventario.TIPO_SALIDA,
                cantidad=restante,
                motivo=MovimientoInventario.MOTIVO_VENTA_POS,
                destino=MovimientoInventario.DESTINO_WEB,
                usuario=usuario,
            )
