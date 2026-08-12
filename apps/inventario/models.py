from django.db import models
from django.conf import settings
from apps.tienda.models import Producto


class MovimientoInventario(models.Model):
    TIPO_ENTRADA = 'entrada'
    TIPO_SALIDA = 'salida'

    TIPO_CHOICES = [
        (TIPO_ENTRADA, 'Entrada (Ingreso)'),
        (TIPO_SALIDA, 'Salida (Egreso)'),
    ]

    DESTINO_TIENDA = 'tienda'
    DESTINO_WEB = 'web'
    DESTINO_CHOICES = [
        (DESTINO_TIENDA, 'Stock tienda (POS)'),
        (DESTINO_WEB, 'Stock web'),
    ]

    MOTIVO_COMPRA = 'compra'
    MOTIVO_VENTA_WEB = 'venta_web'
    MOTIVO_VENTA_POS = 'venta_pos'
    MOTIVO_AJUSTE = 'ajuste'
    MOTIVO_MANTENIMIENTO = 'mantenimiento'
    MOTIVO_RESERVA_WEB = 'reserva_web'
    MOTIVO_LIBERACION_WEB = 'liberacion_web'
    MOTIVO_TRANSFERENCIA = 'transferencia'

    MOTIVO_CHOICES = [
        (MOTIVO_COMPRA, 'Compra / Abastecimiento'),
        (MOTIVO_VENTA_WEB, 'Venta Web'),
        (MOTIVO_VENTA_POS, 'Venta POS / Tienda'),
        (MOTIVO_AJUSTE, 'Ajuste de Inventario'),
        (MOTIVO_MANTENIMIENTO, 'Repuestos Mantenimiento'),
        (MOTIVO_RESERVA_WEB, 'Reserva pedido web'),
        (MOTIVO_LIBERACION_WEB, 'Liberación reserva web'),
        (MOTIVO_TRANSFERENCIA, 'Transferencia tienda ↔ web'),
    ]

    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='movimientos',
        verbose_name="Producto"
    )
    tipo = models.CharField(
        max_length=10,
        choices=TIPO_CHOICES,
        verbose_name="Tipo de Movimiento"
    )
    cantidad = models.IntegerField(verbose_name="Cantidad")
    motivo = models.CharField(
        max_length=20,
        choices=MOTIVO_CHOICES,
        default=MOTIVO_AJUSTE,
        verbose_name="Motivo"
    )
    destino = models.CharField(
        max_length=10,
        choices=DESTINO_CHOICES,
        default=DESTINO_TIENDA,
        db_index=True,
        verbose_name="Destino de stock",
        help_text="Indica si el movimiento afecta stock tienda o stock web.",
    )
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="Registrado por"
    )

    class Meta:
        verbose_name = "Movimiento de Inventario"
        verbose_name_plural = "Movimientos de Inventario"
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.cantidad} uds. de {self.producto.codigo_articulo}"

    def _debe_afectar_web(self) -> bool:
        if self.destino == self.DESTINO_WEB:
            return True
        # Compatibilidad con movimientos viejos (sin destino explícito)
        return self.motivo in (
            self.MOTIVO_VENTA_WEB,
            self.MOTIVO_RESERVA_WEB,
            self.MOTIVO_LIBERACION_WEB,
        )

    def save(self, *args, **kwargs):
        # Actualiza stock tienda o web según destino / motivo.
        skip = getattr(self, '_skip_stock', False) or kwargs.pop('skip_stock', False)
        if not self.pk and not skip:
            # Inferir destino desde motivo si no se fijó (ventas/reservas web)
            if self.destino == self.DESTINO_TIENDA and self.motivo in (
                self.MOTIVO_VENTA_WEB,
                self.MOTIVO_RESERVA_WEB,
                self.MOTIVO_LIBERACION_WEB,
            ):
                self.destino = self.DESTINO_WEB

            producto = self.producto
            afecta_web = self._debe_afectar_web()
            if self.tipo == self.TIPO_ENTRADA:
                if afecta_web:
                    producto.stock_web += self.cantidad
                    producto.save(update_fields=['stock_web'])
                else:
                    producto.stock += self.cantidad
                    producto.save(update_fields=['stock'])
            elif self.tipo == self.TIPO_SALIDA:
                if afecta_web:
                    producto.stock_web = max(0, producto.stock_web - self.cantidad)
                    producto.save(update_fields=['stock_web'])
                else:
                    producto.stock = max(0, producto.stock - self.cantidad)
                    producto.save(update_fields=['stock'])

        super().save(*args, **kwargs)
