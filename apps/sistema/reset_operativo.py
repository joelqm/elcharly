"""
Reinicio de data operativa (pruebas → producción limpia).

Conserva: productos, categorías, imágenes, atributos, usuarios, sedes/empresa,
clientes y configuración del correlativo OT.
Elimina: ventas, pagos, caja, movimientos de stock, OT, cotizaciones, logs.
Pone stock tienda/web en 0.
"""
from __future__ import annotations

from django.db import transaction


def reiniciar_data_operativa(*, wipe_import_logs: bool = True) -> dict:
    """
    Vacía tablas transaccionales. Nunca borra clientes ni toca ContadorOT.
    Retorna conteos eliminados / actualizados.
    """
    from apps.pagos.models import Pago
    from apps.pos.models import TicketPOS, MovimientoCaja, CajaSesion
    from apps.pedidos.models import DetallePedido, Pedido
    from apps.cotizaciones.models import DetalleCotizacion, Cotizacion
    from apps.mantenimiento.models import (
        OrdenTrabajoLinea, Mantenimiento, EquipoRegistrado,
    )
    from apps.inventario.models import MovimientoInventario
    from apps.sistema.models import LogActividad
    from apps.tienda.models import Producto, StockSede, ImportacionCatalogo, LogCambioImportacion

    stats = {}

    with transaction.atomic():
        stats['pagos'] = Pago.objects.all().delete()[0]
        stats['tickets_pos'] = TicketPOS.objects.all().delete()[0]
        stats['movimientos_caja'] = MovimientoCaja.objects.all().delete()[0]
        stats['detalle_pedido'] = DetallePedido.objects.all().delete()[0]
        stats['detalle_cotizacion'] = DetalleCotizacion.objects.all().delete()[0]
        stats['lineas_ot'] = OrdenTrabajoLinea.objects.all().delete()[0]
        for m in Mantenimiento.objects.all().iterator():
            m.repuestos_usados.clear()
        stats['mantenimientos'] = Mantenimiento.objects.all().delete()[0]
        stats['equipos'] = EquipoRegistrado.objects.all().delete()[0]
        stats['pedidos'] = Pedido.objects.all().delete()[0]
        stats['cajas'] = CajaSesion.objects.all().delete()[0]
        stats['cotizaciones'] = Cotizacion.objects.all().delete()[0]
        stats['movimientos_inventario'] = MovimientoInventario.objects.all().delete()[0]
        stats['log_actividad'] = LogActividad.objects.all().delete()[0]

        if wipe_import_logs:
            stats['log_importacion'] = LogCambioImportacion.objects.all().delete()[0]
            stats['importaciones'] = ImportacionCatalogo.objects.all().delete()[0]
        else:
            stats['log_importacion'] = 0
            stats['importaciones'] = 0

        stats['clientes'] = 'conservados'
        stats['correlativo_ot'] = 'sin cambios (configurable en Respaldo)'

        stock_n = Producto.objects.update(stock=0, stock_web=0, venta_bloqueada=False)
        stats['productos_stock_cero'] = stock_n
        sede_n = StockSede.objects.update(cantidad=0)
        stats['stock_sede_cero'] = sede_n

        try:
            from django.contrib.sessions.models import Session
            stats['sesiones_web'] = Session.objects.all().delete()[0]
        except Exception:
            stats['sesiones_web'] = 0

    return stats
