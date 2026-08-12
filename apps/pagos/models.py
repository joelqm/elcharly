from django.db import models
from apps.pedidos.models import Pedido

class Pago(models.Model):
    METODO_EFECTIVO = 'efectivo'
    METODO_YAPE = 'yape'
    METODO_PLIN = 'plin'
    METODO_TARJETA = 'tarjeta'
    METODO_TRANSFERENCIA = 'transferencia'
    METODO_TIENDA = 'tienda'

    METODO_CHOICES = [
        (METODO_EFECTIVO, 'Efectivo'),
        (METODO_YAPE, 'Yape'),
        (METODO_PLIN, 'Plin'),
        (METODO_TARJETA, 'Tarjeta Crédito/Débito'),
        (METODO_TRANSFERENCIA, 'Transferencia Bancaria'),
        (METODO_TIENDA, 'Pagar en tienda'),
    ]

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_APROBADO = 'aprobado'
    ESTADO_RECHAZADO = 'rechazado'
    ESTADO_REEMBOLSADO = 'reembolsado'

    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente de Confirmación'),
        (ESTADO_APROBADO, 'Aprobado / Pagado'),
        (ESTADO_RECHAZADO, 'Rechazado'),
        (ESTADO_REEMBOLSADO, 'Reembolsado'),
    ]

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='pagos',
        verbose_name="Pedido"
    )
    metodo = models.CharField(
        max_length=20,
        choices=METODO_CHOICES,
        default=METODO_TARJETA,
        verbose_name="Método de Pago"
    )
    monto = models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Monto Pagado")
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE,
        verbose_name="Estado del Pago"
    )
    referencia_externa = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Referencia Pasarela (ID Transacción)"
    )
    voucher = models.ImageField(
        upload_to='vouchers/pagos/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Voucher / captura de pago',
    )
    fecha_pago = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Pago")

    class Meta:
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"
        ordering = ['-fecha_pago']

    def __str__(self):
        return f"Pago {self.id} - {self.pedido.numero_pedido} ({self.get_estado_display()})"

    def save(self, *args, **kwargs):
        """Al aprobar un pago, avanza el pedido sin rebajar estados finales.

        - POS: entregado (cliente ya se lleva el producto)
        - Web: pagado (luego listo/entrega en tienda)
        - No toca enviado / entregado / cancelado
        """
        super().save(*args, **kwargs)
        if self.estado != self.ESTADO_APROBADO:
            return
        pedido = self.pedido
        if pedido.estado in (
            Pedido.ESTADO_ENTREGADO,
            Pedido.ESTADO_ENVIADO,
            Pedido.ESTADO_CANCELADO,
        ):
            return
        nuevo = (
            Pedido.ESTADO_ENTREGADO
            if pedido.canal == Pedido.CANAL_POS
            else Pedido.ESTADO_PAGADO
        )
        if pedido.estado != nuevo:
            pedido.estado = nuevo
            pedido.save(update_fields=['estado'])
