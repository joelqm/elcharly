from django.db import models
from django.conf import settings
from apps.pedidos.models import Pedido

class CajaSesion(models.Model):
    ESTADO_ABIERTA = 'abierta'
    ESTADO_CERRADA = 'cerrada'
    ESTADO_CHOICES = [
        (ESTADO_ABIERTA, 'Abierta'),
        (ESTADO_CERRADA, 'Cerrada'),
    ]

    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sesiones_caja',
        verbose_name="Cajero"
    )
    sede = models.ForeignKey(
        'sistema.Sede',
        on_delete=models.PROTECT,
        related_name='sesiones_caja',
        null=True,
        blank=True,
        verbose_name='Sede',
    )
    fecha_apertura = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Apertura")
    fecha_cierre = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Cierre")
    monto_apertura = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto de Apertura")
    monto_cierre = models.DecimalField(null=True, blank=True, max_digits=10, decimal_places=2, verbose_name="Monto de Cierre")
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ESTADO_ABIERTA, verbose_name="Estado")
    observaciones = models.TextField(null=True, blank=True, verbose_name="Observaciones")

    class Meta:
        verbose_name = "Sesión de Caja"
        verbose_name_plural = "Sesiones de Caja"
        ordering = ['-fecha_apertura']

    def __str__(self):
        sede = f' · {self.sede.codigo}' if self.sede_id else ''
        return f"Caja {self.id}{sede} - {self.cajero.username} ({self.get_estado_display()})"

    def total_movimientos_neto(self):
        """Ingresos − egresos de la gaveta (sin ventas)."""
        from decimal import Decimal
        from django.db.models import Sum, Q
        agg = self.movimientos.aggregate(
            ingresos=Sum('monto', filter=Q(tipo=MovimientoCaja.TIPO_INGRESO)),
            egresos=Sum('monto', filter=Q(tipo=MovimientoCaja.TIPO_EGRESO)),
        )
        ingresos = agg['ingresos'] or Decimal('0.00')
        egresos = agg['egresos'] or Decimal('0.00')
        return ingresos - egresos


class TicketPOS(models.Model):
    TIPO_TICKET = 'ticket'
    TIPO_BOLETA = 'boleta'
    TIPO_FACTURA = 'factura'
    
    TIPO_COMPROBANTE_CHOICES = [
        (TIPO_TICKET, 'Ticket Simple'),
        (TIPO_BOLETA, 'Boleta de Venta'),
        (TIPO_FACTURA, 'Factura'),
    ]

    numero_serie = models.CharField(max_length=50, unique=True, db_index=True, verbose_name="Número de Serie")
    pedido = models.OneToOneField(Pedido, on_delete=models.CASCADE, related_name='ticket_pos', verbose_name="Pedido")
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='tickets_emitidos',
        verbose_name="Cajero"
    )
    fecha_emision = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Emisión")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Subtotal")
    igv = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="IGV (18%)")
    total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total")
    tipo_comprobante = models.CharField(max_length=20, choices=TIPO_COMPROBANTE_CHOICES, default=TIPO_TICKET, verbose_name="Tipo de Comprobante")
    ruc_cliente = models.CharField(max_length=11, blank=True, null=True, verbose_name="RUC")
    razon_social = models.CharField(max_length=255, blank=True, null=True, verbose_name="Razón Social")
    impreso = models.BooleanField(default=False, verbose_name="Impreso")

    class Meta:
        verbose_name = "Ticket POS"
        verbose_name_plural = "Tickets POS"
        ordering = ['-fecha_emision']

    def __str__(self):
        return f"{self.numero_serie} - {self.get_tipo_comprobante_display()} - Total: S/. {self.total}"

    def save(self, *args, **kwargs):
        if not self.numero_serie:
            from apps.pos.correlativos import serie_para_tipo, siguiente_numero

            # Si el pedido ya tiene correlativo SUNAT (R001/B001/F001), reutilizarlo.
            pedido_num = ''
            if self.pedido_id:
                pedido_num = (getattr(self.pedido, 'numero_pedido', None) or '').strip()
            if pedido_num and len(pedido_num) >= 6 and pedido_num[0] in 'RBF' and '-' in pedido_num:
                self.numero_serie = pedido_num
            else:
                self.numero_serie = siguiente_numero(serie_para_tipo(self.tipo_comprobante))
        super().save(*args, **kwargs)


class MovimientoCaja(models.Model):
    """Ingresos y egresos de efectivo de la gaveta (aparte de ventas)."""

    TIPO_INGRESO = 'ingreso'
    TIPO_EGRESO = 'egreso'
    TIPO_CHOICES = [
        (TIPO_INGRESO, 'Ingreso'),
        (TIPO_EGRESO, 'Egreso'),
    ]

    MOTIVO_SENCILLO = 'sencillo'
    MOTIVO_ALQUILER = 'alquiler'
    MOTIVO_SERVICIOS = 'servicios'
    MOTIVO_RETIRO = 'retiro'
    MOTIVO_APORTE = 'aporte'
    MOTIVO_OTRO = 'otro'
    MOTIVO_CHOICES = [
        (MOTIVO_SENCILLO, 'Sencillo / cambio'),
        (MOTIVO_APORTE, 'Aporte de efectivo'),
        (MOTIVO_ALQUILER, 'Alquiler'),
        (MOTIVO_SERVICIOS, 'Servicios / pagos'),
        (MOTIVO_RETIRO, 'Retiro / sangría'),
        (MOTIVO_OTRO, 'Otro'),
    ]

    sesion = models.ForeignKey(
        CajaSesion,
        on_delete=models.CASCADE,
        related_name='movimientos',
        verbose_name='Sesión de caja',
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, verbose_name='Tipo')
    motivo = models.CharField(max_length=20, choices=MOTIVO_CHOICES, default=MOTIVO_OTRO)
    monto = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Monto')
    concepto = models.CharField(max_length=255, blank=True, default='', verbose_name='Concepto / detalle')
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='movimientos_caja',
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Movimiento de caja'
        verbose_name_plural = 'Movimientos de caja'
        ordering = ['-fecha']

    def __str__(self):
        signo = '+' if self.tipo == self.TIPO_INGRESO else '−'
        return f"{signo}S/ {self.monto} · {self.get_motivo_display()}"

    @property
    def afecta_efectivo(self):
        """Ingreso suma a gaveta; egreso resta."""
        return self.tipo == self.TIPO_INGRESO

