from django.db import models
from django.conf import settings
from apps.clientes.models import Cliente
from apps.tienda.models import Producto

class Pedido(models.Model):
    CANAL_WEB = 'web'
    CANAL_POS = 'pos'
    CANAL_COTIZACION = 'cotizacion'

    CANAL_CHOICES = [
        (CANAL_WEB, 'Venta Web'),
        (CANAL_POS, 'Venta POS (Tienda Física)'),
        (CANAL_COTIZACION, 'Desde Cotización'),
    ]

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_PAGADO = 'pagado'
    ESTADO_ENVIADO = 'enviado'
    ESTADO_ENTREGADO = 'entregado'
    ESTADO_CANCELADO = 'cancelado'

    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente de Pago'),
        (ESTADO_PAGADO, 'Pagado'),
        (ESTADO_ENVIADO, 'Listo para recojo'),
        (ESTADO_ENTREGADO, 'Entregado / Retirado'),
        (ESTADO_CANCELADO, 'Cancelado'),
    ]

    # Ventas concretadas (para CRM, reportes, KPIs). Incluye POS entregado.
    ESTADOS_CONCRETADOS = (ESTADO_PAGADO, ESTADO_ENVIADO, ESTADO_ENTREGADO)

    numero_pedido = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="Número de Pedido"
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name='pedidos',
        verbose_name="Cliente"
    )
    canal = models.CharField(
        max_length=20,
        choices=CANAL_CHOICES,
        default=CANAL_WEB,
        verbose_name="Canal de Venta"
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE,
        verbose_name="Estado de Pedido"
    )
    fecha_pedido = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Pedido")
    
    # Montos
    subtotal = models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Subtotal")
    igv = models.DecimalField(decimal_places=2, max_digits=10, verbose_name="IGV (18%)")
    total = models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Total")
    
    direccion_envio = models.CharField(max_length=255, blank=True, null=True, verbose_name="Dirección de Envío")
    notas = models.TextField(blank=True, null=True, verbose_name="Notas / Instrucciones")
    
    atendido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='pedidos_atendidos',
        verbose_name="Atendido por"
    )
    caja_sesion = models.ForeignKey(
        'pos.CajaSesion',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='pedidos',
        verbose_name="Sesión de Caja"
    )
    sede = models.ForeignKey(
        'sistema.Sede',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='pedidos',
        verbose_name='Sede',
    )
    # Reserva web: stock descontado hasta pagar o liberar (24h)
    stock_reservado = models.BooleanField(default=False)
    reservado_hasta = models.DateTimeField(blank=True, null=True, db_index=True)
    voucher = models.ImageField(upload_to='vouchers/%Y/%m/', blank=True, null=True)

    class Meta:
        verbose_name = "Pedido / Venta"
        verbose_name_plural = "Pedidos y ventas"
        ordering = ['-fecha_pedido']

    def __str__(self):
        return f"{self.numero_pedido} - {self.cliente.nombre_completo} ({self.get_estado_display()})"

    def _prefijo_numero(self):
        if self.canal == self.CANAL_POS:
            return 'VTA'
        if self.canal == self.CANAL_COTIZACION:
            return 'COT'
        return 'WEB'

    def save(self, *args, **kwargs):
        if not self.numero_pedido:
            import datetime
            year = datetime.datetime.now().year
            prefijo = self._prefijo_numero()
            candidatos = Pedido.objects.filter(numero_pedido__startswith=f"{prefijo}-{year}-")
            if prefijo == 'WEB':
                candidatos = Pedido.objects.filter(
                    models.Q(numero_pedido__startswith=f"WEB-{year}-")
                    | models.Q(numero_pedido__startswith=f"ORD-{year}-")
                )
            last_order = candidatos.order_by('-id').first()
            if last_order:
                try:
                    last_num = int(last_order.numero_pedido.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            self.numero_pedido = f"{prefijo}-{year}-{new_num:04d}"
        super().save(*args, **kwargs)


class PedidoWeb(Pedido):
    """Pedidos del e-commerce (catálogo / checkout web)."""

    class Meta:
        proxy = True
        verbose_name = "Pedido web"
        verbose_name_plural = "Pedidos web"


class VentaTienda(Pedido):
    """Ventas registradas en tienda física (POS)."""

    class Meta:
        proxy = True
        verbose_name = "Venta de tienda"
        verbose_name_plural = "Ventas de tienda"


class PedidoDesdeCotizacion(Pedido):
    """Pedidos generados a partir de una cotización."""

    class Meta:
        proxy = True
        verbose_name = "Pedido desde cotización"
        verbose_name_plural = "Pedidos desde cotización"


class DetallePedido(models.Model):
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='detalles',
        verbose_name="Pedido"
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name='detalles_pedidos',
        verbose_name="Producto"
    )
    # Instantánea al vender: no cambia si luego se reimporta el catálogo
    codigo_articulo = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name="Código al momento de la venta",
    )
    nombre_producto = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="Nombre al momento de la venta",
        help_text="Se congela al crear la línea. Un cambio de precio/nombre en el Excel no altera ventas antiguas.",
    )
    cantidad = models.PositiveIntegerField(verbose_name="Cantidad")
    precio_unitario = models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Precio Unitario")
    subtotal = models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Subtotal")

    class Meta:
        verbose_name = "Detalle de Pedido"
        verbose_name_plural = "Detalles de Pedidos"

    def __str__(self):
        cod = self.codigo_linea
        return f"{self.cantidad} uds. de {cod} en {self.pedido.numero_pedido}"

    @property
    def codigo_linea(self):
        """Código mostrado en tickets/historial (instantánea)."""
        if self.codigo_articulo:
            return self.codigo_articulo
        if self.producto_id:
            return self.producto.codigo_articulo
        return ''

    @property
    def nombre_linea(self):
        """Nombre mostrado en tickets/historial (instantánea)."""
        if self.nombre_producto:
            return self.nombre_producto
        if self.producto_id:
            return self.producto.nombre
        return ''

    def save(self, *args, **kwargs):
        # Congelar nombre/código solo al crear (o si aún están vacíos)
        if self.producto_id:
            if not self.nombre_producto:
                self.nombre_producto = (self.producto.nombre or '')[:255]
            if not self.codigo_articulo:
                self.codigo_articulo = (self.producto.codigo_articulo or '')[:50]
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)
