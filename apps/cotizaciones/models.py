import uuid
from django.db import models
from django.conf import settings
from decimal import Decimal
from urllib.parse import quote
from apps.clientes.models import Cliente
from apps.tienda.models import Producto

# Formato documento STA (Servicio Técnico Autorizado El Charly)
NUMERO_PREFIX = 'STAEC-C-'
VALIDEZ_DIAS_DEFAULT = 5


def observaciones_default(whatsapp_display: str | None = None) -> list[str]:
    """Textos del pie de cotización (editables por cotización)."""
    wa = (whatsapp_display or '').strip() or '960 160 842'
    return [
        'Monto Total incluye IGV',
        f'Esta cotización tiene una validez de {VALIDEZ_DIAS_DEFAULT} días a partir de la fecha de emisión.',
        f'Celular: {wa} - Cotizaciones',
    ]


class Cotizacion(models.Model):
    ESTADO_BORRADOR = 'borrador'
    ESTADO_ENVIADA = 'enviada'
    ESTADO_APROBADA = 'aprobada'
    ESTADO_RECHAZADA = 'rechazada'
    ESTADO_ANULADA = 'anulada'

    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, 'Borrador'),
        (ESTADO_ENVIADA, 'Enviada al Cliente'),
        (ESTADO_APROBADA, 'Aprobada (Convertida)'),
        (ESTADO_RECHAZADA, 'Rechazada'),
        (ESTADO_ANULADA, 'Anulada'),
    ]

    ESTADOS_EDITABLES = (ESTADO_BORRADOR, ESTADO_ENVIADA, ESTADO_RECHAZADA)
    ESTADOS_ANULABLES = (ESTADO_BORRADOR, ESTADO_ENVIADA, ESTADO_RECHAZADA)

    token_publico = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        verbose_name="Token de acceso público",
    )
    numero = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="Número de Cotización",
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='cotizaciones',
        verbose_name="Cliente CRM",
    )

    nombre_cliente_temporal = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nombre Cliente (Manual)")
    dni_ruc_cliente_temporal = models.CharField(max_length=20, blank=True, null=True, verbose_name="DNI/RUC (Manual)")
    correo_cliente_temporal = models.EmailField(blank=True, null=True, verbose_name="Correo (Manual)")
    telefono_cliente_temporal = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono (Manual)")
    direccion_cliente_temporal = models.CharField(max_length=255, blank=True, null=True, verbose_name="Dirección (Manual)")

    modelo_equipo = models.CharField(max_length=255, blank=True, null=True, verbose_name="Modelo de Equipo")
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_BORRADOR,
        verbose_name="Estado",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")
    fecha_vencimiento = models.DateField(blank=True, null=True, verbose_name="Fecha de Vencimiento")

    subtotal = models.DecimalField(decimal_places=2, max_digits=10, default=Decimal('0.00'), verbose_name="Subtotal")
    igv = models.DecimalField(decimal_places=2, max_digits=10, default=Decimal('0.00'), verbose_name="IGV (18%)")
    total = models.DecimalField(decimal_places=2, max_digits=10, default=Decimal('0.00'), verbose_name="Total")

    # Líneas del pie del PDF/Excel (editables). Si vacío, se usan las de observaciones_default().
    observaciones = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Observaciones / notas importantes (PDF)",
    )
    notas = models.TextField(blank=True, null=True, verbose_name="Notas internas")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='cotizaciones_creadas',
        verbose_name="Creado por",
    )

    class Meta:
        verbose_name = "Cotización"
        verbose_name_plural = "Cotizaciones"
        ordering = ['-fecha_creacion']

    def __str__(self):
        cliente_nombre = self.cliente.nombre_completo if self.cliente else self.nombre_cliente_temporal or "Cliente Anónimo"
        return f"{self.numero} - {cliente_nombre} ({self.get_estado_display()})"

    @property
    def cliente_nombre(self):
        if self.cliente_id:
            return self.cliente.nombre_completo
        return self.nombre_cliente_temporal or ''

    @property
    def cliente_ruc(self):
        if self.cliente_id:
            return self.cliente.dni_ruc
        return self.dni_ruc_cliente_temporal or ''

    @property
    def cliente_telefono(self):
        if self.cliente_id:
            return self.cliente.telefono or ''
        return self.telefono_cliente_temporal or ''

    @property
    def cliente_direccion(self):
        if self.cliente_id:
            return self.cliente.direccion or ''
        return self.direccion_cliente_temporal or ''

    def lineas_observaciones(self):
        """Observaciones públicas para PDF/Excel."""
        raw = self.observaciones
        if isinstance(raw, list):
            lines = [str(x).strip() for x in raw if str(x).strip()]
            if lines:
                return lines
        from django.conf import settings
        negocio = getattr(settings, 'NEGOCIO', {}) or {}
        return observaciones_default(negocio.get('whatsapp_display'))

    def obtener_url_publica(self, request=None):
        """Retorna la URL pública de la cotización."""
        from django.urls import reverse
        rel = reverse('cotizaciones:publica_ver', kwargs={'token': self.token_publico})
        if request:
            return request.build_absolute_uri(rel)
        return rel

    def obtener_link_whatsapp(self, request=None):
        """Genera el enlace listo para enviar por WhatsApp."""
        from re import sub
        raw_phone = self.cliente_telefono or ''
        digits = sub(r'\D', '', raw_phone)
        if digits and not digits.startswith('51') and len(digits) == 9:
            digits = '51' + digits

        url_pub = self.obtener_url_publica(request=request)
        nombre = self.cliente_nombre or 'Estimado(a) cliente'
        msj = (
            f"Hola *{nombre}*, le compartimos la Cotización *{self.numero}* de "
            f"Servicio Técnico Autorizado Makita - El Charly.\n\n"
            f"📌 *Monto Total:* S/ {self.total:,.2f}\n"
            f"📄 *Ver/Descargar Cotización:* {url_pub}\n\n"
            f"Gracias por su preferencia."
        )
        msj_encoded = quote(msj)
        if digits:
            return f"https://api.whatsapp.com/send?phone={digits}&text={msj_encoded}"
        return f"https://api.whatsapp.com/send?text={msj_encoded}"

    @classmethod
    def max_correlativo(cls):
        """Mayor N entero al final del correlativo (funciona con cualquier prefijo)."""
        import re
        max_n = 0
        for num in cls.objects.values_list('numero', flat=True):
            match = re.search(r'(\d+)$', str(num).strip())
            if match:
                try:
                    max_n = max(max_n, int(match.group(1)))
                except ValueError:
                    pass
        return max_n

    @classmethod
    def siguiente_numero(cls):
        """Siguiente número de cotización con el prefijo configurado."""
        return f'{NUMERO_PREFIX}{cls.max_correlativo() + 1}'

    @property
    def puede_editar(self):
        return self.estado in self.ESTADOS_EDITABLES

    @property
    def puede_anular(self):
        return self.estado in self.ESTADOS_ANULABLES

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = self.siguiente_numero()
        if not self.fecha_vencimiento:
            import datetime
            self.fecha_vencimiento = datetime.date.today() + datetime.timedelta(days=VALIDEZ_DIAS_DEFAULT)
        super().save(*args, **kwargs)

    def calcular_totales(self):
        """Los precios de línea son con IGV (precio al cliente)."""
        items = self.detalles.all()
        total_sum = sum((item.subtotal for item in items), Decimal('0.00'))
        self.total = Decimal(str(total_sum)).quantize(Decimal('0.01'))
        self.subtotal = (self.total / Decimal('1.18')).quantize(Decimal('0.01'))
        self.igv = (self.total - self.subtotal).quantize(Decimal('0.01'))
        self.save(update_fields=['total', 'subtotal', 'igv'])


class DetalleCotizacion(models.Model):
    cotizacion = models.ForeignKey(
        Cotizacion,
        on_delete=models.CASCADE,
        related_name='detalles',
        verbose_name="Cotización",
    )
    repuesto = models.ForeignKey(
        Producto,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='detalles_cotizados',
        verbose_name="Producto catálogo",
    )
    codigo_articulo = models.CharField(max_length=50, blank=True, default='', verbose_name="Código")
    descripcion = models.CharField(max_length=255, blank=True, default='', verbose_name="Descripción")
    descripcion_manual = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Descripción Manual (legacy)",
    )
    cantidad = models.PositiveIntegerField(default=1, verbose_name="Cantidad")
    # Precio al cliente (con IGV) — sale en PDF/Excel
    precio_unitario = models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Precio unitario (con IGV)")
    # Solo internos (no se imprimen)
    precio_lista = models.DecimalField(
        decimal_places=2, max_digits=12, default=Decimal('0.00'),
        verbose_name="Precio lista sin IGV (interno)",
    )
    precio_costo = models.DecimalField(
        decimal_places=2, max_digits=12, default=Decimal('0.00'),
        verbose_name="Precio compra / costo (interno)",
    )
    subtotal = models.DecimalField(decimal_places=2, max_digits=10, default=Decimal('0.00'), verbose_name="Valor / subtotal")

    class Meta:
        verbose_name = "Detalle de Cotización"
        verbose_name_plural = "Detalles de Cotización"

    def __str__(self):
        return f"{self.cantidad} x {self.descripcion_linea} - {self.cotizacion.numero}"

    @property
    def imagen_url(self):
        if self.repuesto_id:
            return self.repuesto.imagen_destacada_url
        return None

    @property
    def descripcion_linea(self):
        return (
            (self.descripcion or '').strip()
            or (self.descripcion_manual or '').strip()
            or (self.repuesto.nombre if self.repuesto_id else '')
            or 'Ítem'
        )

    @property
    def codigo_linea(self):
        if self.codigo_articulo:
            return self.codigo_articulo
        if self.repuesto_id:
            return self.repuesto.codigo_articulo
        return ''

    @property
    def margen_pct(self):
        """Margen sobre precio de venta con IGV (solo interno)."""
        venta = Decimal(str(self.precio_unitario or 0))
        costo = Decimal(str(self.precio_costo or 0))
        if venta <= 0:
            return None
        return ((venta - costo) / venta * Decimal('100')).quantize(Decimal('0.1'))

    def save(self, *args, **kwargs):
        if self.repuesto_id:
            if not self.codigo_articulo:
                self.codigo_articulo = self.repuesto.codigo_articulo or ''
            if not self.descripcion:
                self.descripcion = (self.descripcion_manual or self.repuesto.nombre or '')[:255]
        elif self.descripcion_manual and not self.descripcion:
            self.descripcion = self.descripcion_manual[:255]
        self.subtotal = (Decimal(str(self.cantidad)) * Decimal(str(self.precio_unitario))).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)
        self.cotizacion.calcular_totales()
