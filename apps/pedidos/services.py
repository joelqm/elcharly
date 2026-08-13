"""Servicios compartidos de pedidos (web, POS, aprobación de pagos)."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.inventario.models import MovimientoInventario
from apps.mantenimiento.models import registrar_equipos_pedido
from apps.pagos.models import Pago


class StockInsuficienteError(Exception):
    """Se lanza cuando no hay stock suficiente para completar una venta."""

    def __init__(self, mensaje):
        self.mensaje = mensaje
        super().__init__(mensaje)


def validar_stock_pedido(pedido):
    """Valida stock disponible (tienda o web según canal del pedido)."""
    from apps.pedidos.models import Pedido
    from apps.sistema.stock import stock_para_venta

    errores = []
    usar_web = pedido.canal != Pedido.CANAL_POS
    for detalle in pedido.detalles.select_related('producto'):
        if usar_web:
            if pedido.stock_reservado:
                continue  # ya descontado
            disponible = detalle.producto.stock_web
        else:
            disponible = stock_para_venta(detalle.producto, getattr(pedido, 'sede', None))
        if disponible < detalle.cantidad:
            errores.append(
                f"{detalle.nombre_linea}: solicitado {detalle.cantidad}, "
                f"disponible {disponible}"
            )
    if errores:
        raise StockInsuficienteError(
            "Stock insuficiente. " + "; ".join(errores)
        )


def descontar_inventario_pedido(pedido, motivo, usuario=None):
    """
    Crea salidas de inventario por cada ítem del pedido.
    En venta POS descuenta tienda primero y completa desde web automáticamente.
    """
    from apps.sistema.stock import descontar_stock_pos
    from apps.tienda.models import StockSede

    sede = getattr(pedido, 'sede', None)

    if motivo == MovimientoInventario.MOTIVO_VENTA_POS:
        for detalle in pedido.detalles.select_related('producto'):
            try:
                descontar_stock_pos(
                    detalle.producto,
                    detalle.cantidad,
                    sede=sede,
                    usuario=usuario,
                )
            except ValueError as exc:
                raise StockInsuficienteError(str(exc)) from exc
        return

    for detalle in pedido.detalles.select_related('producto'):
        producto = detalle.producto
        cantidad = detalle.cantidad

        if (
            sede is not None
            and not sede.compartir_productos
        ):
            row, _ = StockSede.objects.select_for_update().get_or_create(
                producto=producto, sede=sede, defaults={'cantidad': 0},
            )
            row.cantidad = max(0, row.cantidad - cantidad)
            row.save(update_fields=['cantidad'])
            mov = MovimientoInventario(
                producto=producto,
                tipo=MovimientoInventario.TIPO_SALIDA,
                cantidad=cantidad,
                motivo=motivo,
                usuario=usuario,
            )
            mov._skip_stock = True
            mov.save()
        else:
            MovimientoInventario.objects.create(
                producto=producto,
                tipo=MovimientoInventario.TIPO_SALIDA,
                cantidad=cantidad,
                motivo=motivo,
                usuario=usuario,
            )


@transaction.atomic
def reservar_stock_web(pedido, horas=24):
    """Reserva stock_web al crear pedido pendiente (Yape / tienda)."""
    if pedido.stock_reservado:
        return
    validar_stock_pedido(pedido)
    for detalle in pedido.detalles.select_related('producto'):
        MovimientoInventario.objects.create(
            producto=detalle.producto,
            tipo=MovimientoInventario.TIPO_SALIDA,
            cantidad=detalle.cantidad,
            motivo=MovimientoInventario.MOTIVO_RESERVA_WEB,
        )
    pedido.stock_reservado = True
    pedido.reservado_hasta = timezone.now() + timedelta(hours=horas)
    pedido.save(update_fields=['stock_reservado', 'reservado_hasta'])


@transaction.atomic
def liberar_reserva_pedido(pedido, motivo='Expiró plazo de pago (24h)'):
    """Devuelve stock_web y cancela el pedido pendiente."""
    from apps.pedidos.models import Pedido

    if pedido.estado != Pedido.ESTADO_PENDIENTE:
        return False
    if pedido.stock_reservado:
        for detalle in pedido.detalles.select_related('producto'):
            MovimientoInventario.objects.create(
                producto=detalle.producto,
                tipo=MovimientoInventario.TIPO_ENTRADA,
                cantidad=detalle.cantidad,
                motivo=MovimientoInventario.MOTIVO_LIBERACION_WEB,
            )
        pedido.stock_reservado = False
    pedido.estado = Pedido.ESTADO_CANCELADO
    notas = (pedido.notas or '') + f'\n[{motivo}]'
    pedido.notas = notas.strip()
    pedido.save(update_fields=['estado', 'stock_reservado', 'notas'])
    Pago.objects.filter(pedido=pedido, estado=Pago.ESTADO_PENDIENTE).update(
        estado=Pago.ESTADO_RECHAZADO,
    )
    return True


@transaction.atomic
def confirmar_pago_pedido(
    pedido,
    metodo,
    monto=None,
    referencia_externa=None,
    usuario=None,
    motivo_inventario=None,
    pago=None,
    descontar_stock=True,
):
    """
    Marca el pago como aprobado, descuenta inventario y registra equipos.
    Si el stock ya estaba reservado (web), no vuelve a descontar.
    descontar_stock=False: venta histórica (cuaderno), no toca inventario.
    """
    from apps.pedidos.models import Pedido

    if motivo_inventario is None:
        if pedido.canal == Pedido.CANAL_POS:
            motivo_inventario = MovimientoInventario.MOTIVO_VENTA_POS
        else:
            motivo_inventario = MovimientoInventario.MOTIVO_VENTA_WEB

    ya_reservado = bool(pedido.stock_reservado)
    if descontar_stock and not ya_reservado:
        validar_stock_pedido(pedido)

    if pago is None:
        pago = Pago.objects.create(
            pedido=pedido,
            metodo=metodo,
            monto=monto if monto is not None else pedido.total,
            estado=Pago.ESTADO_APROBADO,
            referencia_externa=referencia_externa or '',
        )
    else:
        pago.estado = Pago.ESTADO_APROBADO
        if referencia_externa:
            pago.referencia_externa = referencia_externa
        pago.save()

    if pedido.canal == Pedido.CANAL_POS:
        # Venta presencial: el cliente se lleva el producto al instante.
        if pedido.estado != Pedido.ESTADO_ENTREGADO:
            pedido.estado = Pedido.ESTADO_ENTREGADO
            pedido.save(update_fields=['estado'])
    elif pedido.estado != Pedido.ESTADO_PAGADO:
        pedido.estado = Pedido.ESTADO_PAGADO
        pedido.save(update_fields=['estado'])

    if not descontar_stock:
        pass
    elif ya_reservado:
        # Stock ya bajó en la reserva; solo auditamos como venta web
        for detalle in pedido.detalles.select_related('producto'):
            mov = MovimientoInventario(
                producto=detalle.producto,
                tipo=MovimientoInventario.TIPO_SALIDA,
                cantidad=detalle.cantidad,
                motivo=MovimientoInventario.MOTIVO_VENTA_WEB,
                usuario=usuario,
            )
            mov._skip_stock = True
            mov.save()
        pedido.stock_reservado = False
        pedido.reservado_hasta = None
        pedido.save(update_fields=['stock_reservado', 'reservado_hasta'])
    else:
        descontar_inventario_pedido(pedido, motivo_inventario, usuario=usuario)

    registrar_equipos_pedido(pedido)
    return pago


def devolver_inventario_pedido(pedido, usuario=None):
    """
    Reingresa stock de una venta anulada.
    POS: vuelve a tienda/sede. Web: vuelve a stock_web.
    No aplica a servicios ni a ventas históricas (nunca descontaron).
    """
    from apps.pedidos.models import Pedido
    from apps.tienda.models import Producto, StockSede

    if getattr(pedido, 'es_historica', False):
        return

    sede = getattr(pedido, 'sede', None)
    es_pos = pedido.canal == Pedido.CANAL_POS

    for detalle in pedido.detalles.select_related('producto'):
        producto = detalle.producto
        cantidad = detalle.cantidad
        if cantidad <= 0 or getattr(producto, 'tipo', None) == Producto.TIPO_SERVICIO:
            continue

        if es_pos:
            if sede is not None and not sede.compartir_productos:
                row, _ = StockSede.objects.select_for_update().get_or_create(
                    producto=producto, sede=sede, defaults={'cantidad': 0},
                )
                row.cantidad += cantidad
                row.save(update_fields=['cantidad'])
                mov = MovimientoInventario(
                    producto=producto,
                    tipo=MovimientoInventario.TIPO_ENTRADA,
                    cantidad=cantidad,
                    motivo=MovimientoInventario.MOTIVO_AJUSTE,
                    destino=MovimientoInventario.DESTINO_TIENDA,
                    usuario=usuario,
                )
                mov._skip_stock = True
                mov.save()
            else:
                MovimientoInventario.objects.create(
                    producto=producto,
                    tipo=MovimientoInventario.TIPO_ENTRADA,
                    cantidad=cantidad,
                    motivo=MovimientoInventario.MOTIVO_AJUSTE,
                    destino=MovimientoInventario.DESTINO_TIENDA,
                    usuario=usuario,
                )
        else:
            MovimientoInventario.objects.create(
                producto=producto,
                tipo=MovimientoInventario.TIPO_ENTRADA,
                cantidad=cantidad,
                motivo=MovimientoInventario.MOTIVO_LIBERACION_WEB,
                destino=MovimientoInventario.DESTINO_WEB,
                usuario=usuario,
            )


@transaction.atomic
def anular_pedido(pedido, usuario=None, motivo=''):
    """
    Anula una venta/pedido: estado cancelado, pagos fuera de caja,
    stock de vuelta (si aplica) y equipos dados de baja.
    Conserva el correlativo para auditoría.
    """
    from apps.mantenimiento.models import EquipoRegistrado
    from apps.pedidos.models import Pedido

    if pedido.estado == Pedido.ESTADO_CANCELADO:
        return False

    # Pedido web pendiente con reserva: liberar stock_web y cancelar.
    if (
        pedido.canal != Pedido.CANAL_POS
        and pedido.estado == Pedido.ESTADO_PENDIENTE
        and pedido.stock_reservado
    ):
        liberar_reserva_pedido(pedido, motivo=motivo or 'Anulación manual')
        return True

    habia_stock = (
        not getattr(pedido, 'es_historica', False)
        and pedido.estado in Pedido.ESTADOS_CONCRETADOS
    )
    if habia_stock:
        devolver_inventario_pedido(pedido, usuario=usuario)

    if pedido.stock_reservado:
        pedido.stock_reservado = False
        pedido.reservado_hasta = None

    nota = f"[ANULADA {timezone.localdate().isoformat()}]"
    if motivo:
        nota += f" {motivo}"
    prev = (pedido.notas or '').strip()
    pedido.notas = f'{nota}\n{prev}'.strip() if prev else nota
    pedido.estado = Pedido.ESTADO_CANCELADO
    pedido.save(update_fields=[
        'estado', 'notas', 'stock_reservado', 'reservado_hasta',
    ])

    Pago.objects.filter(pedido=pedido, estado=Pago.ESTADO_APROBADO).update(
        estado=Pago.ESTADO_REEMBOLSADO,
    )
    Pago.objects.filter(pedido=pedido, estado=Pago.ESTADO_PENDIENTE).update(
        estado=Pago.ESTADO_RECHAZADO,
    )

    EquipoRegistrado.objects.filter(
        pedido_origin=pedido,
        estado=EquipoRegistrado.ESTADO_ACTIVO,
    ).update(estado=EquipoRegistrado.ESTADO_BAJA)

    return True


def validar_stock_carrito(cart):
    """Valida stock web de ítems del carrito de sesión. Retorna lista de errores."""
    errores = []
    for item in cart:
        producto = item['producto']
        cantidad = item['cantidad']
        if producto.stock_web < cantidad:
            errores.append(
                f"{producto.nombre}: solicitado {cantidad}, disponible {producto.stock_web}"
            )
    return errores
