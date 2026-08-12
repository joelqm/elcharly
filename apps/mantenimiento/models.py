from django.db import models, transaction
from django.conf import settings
from apps.clientes.models import Cliente
from apps.tienda.models import Producto
from apps.pedidos.models import Pedido
from decimal import Decimal
import re


class ContadorOT(models.Model):
    """
    Configuración del correlativo de Órdenes de Trabajo.
    `ultimo` = último número ya emitido. La siguiente OT será OT-{ultimo+1}.
    Se configura desde Respaldo BD / admin (no está fijo en 612).
    """

    ultimo = models.PositiveIntegerField(
        default=0,
        verbose_name='Último número OT emitido',
        help_text='Si el último papel fue 700, deja 700 aquí: la siguiente será OT-701.',
    )

    class Meta:
        verbose_name = 'Configuración correlativo OT'
        verbose_name_plural = 'Configuración correlativo OT'

    def __str__(self):
        return f'Último OT-{self.ultimo} · siguiente OT-{self.ultimo + 1}'

    @property
    def proximo(self) -> int:
        return int(self.ultimo) + 1

    @classmethod
    def get_solo(cls) -> 'ContadorOT':
        row, _ = cls.objects.get_or_create(pk=1, defaults={'ultimo': 0})
        return row

    @classmethod
    def configurar_proximo(cls, proximo: int) -> 'ContadorOT':
        """Define qué número tendrá la próxima OT (ej. 700 → siguiente OT-700)."""
        proximo = max(1, int(proximo))
        with transaction.atomic():
            row = cls.objects.select_for_update().filter(pk=1).first()
            if not row:
                row = cls(pk=1, ultimo=proximo - 1)
            else:
                row.ultimo = proximo - 1
            row.save()
            return row

    @classmethod
    def siguiente(cls) -> str:
        with transaction.atomic():
            row, _ = cls.objects.select_for_update().get_or_create(pk=1, defaults={'ultimo': 0})
            row.ultimo += 1
            row.save(update_fields=['ultimo'])
            return f'OT-{row.ultimo}'


class EquipoRegistrado(models.Model):
    ESTADO_ACTIVO = 'activo'
    ESTADO_MANTENIMIENTO = 'en_mantenimiento'
    ESTADO_BAJA = 'dado_de_baja'

    ESTADO_CHOICES = [
        (ESTADO_ACTIVO, 'Activo'),
        (ESTADO_MANTENIMIENTO, 'En Mantenimiento'),
        (ESTADO_BAJA, 'Dado de Baja'),
    ]

    ORIGEN_NUESTRO = 'nuestro'
    ORIGEN_EXTERNO = 'externo'
    ORIGEN_CHOICES = [
        (ORIGEN_NUESTRO, 'Vendido por nosotros'),
        (ORIGEN_EXTERNO, 'Otra tienda / externo'),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name='equipos',
        verbose_name='Cliente',
    )
    pedido_origin = models.ForeignKey(
        Pedido,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipos_registrados',
        verbose_name='Pedido de Origen',
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='equipos_registrados',
        verbose_name='Producto de Catálogo',
    )
    modelo_alternativo = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name='Modelo Manual (No Catálogo)',
        help_text='Usar solo si el producto no existe en el catálogo.',
    )
    numero_serie = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        verbose_name='Número de Serie',
    )
    origen = models.CharField(
        max_length=20,
        choices=ORIGEN_CHOICES,
        default=ORIGEN_NUESTRO,
        db_index=True,
        verbose_name='Origen del equipo',
    )
    distribuidor = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Distribuidor / tienda de compra',
        help_text='Si no lo vendimos nosotros (otra tienda Makita).',
    )
    boleta_factura = models.CharField(
        max_length=80,
        blank=True,
        default='',
        verbose_name='Boleta / Factura',
    )
    fecha_compra = models.DateField(null=True, blank=True, verbose_name='Fecha de Compra')
    horas_uso_actuales = models.PositiveIntegerField(default=0, verbose_name='Horas de Uso Actuales')
    horas_proximo_mantenimiento = models.PositiveIntegerField(
        default=300, verbose_name='Próximo Mantenimiento (Horas)'
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_ACTIVO,
        verbose_name='Estado de Equipo',
    )
    garantia_hasta = models.DateField(null=True, blank=True, verbose_name='Garantía Vence El')
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Registro')
    notas = models.TextField(blank=True, default='', verbose_name='Notas')

    class Meta:
        verbose_name = 'Equipo Registrado'
        verbose_name_plural = 'Equipos Registrados'
        ordering = ['-fecha_registro']

    def __str__(self):
        prod_desc = self.producto.nombre if self.producto else self.modelo_alternativo
        return f'{prod_desc} (S/N: {self.numero_serie})'

    @property
    def vendido_por_nosotros(self):
        return self.origen == self.ORIGEN_NUESTRO or bool(self.pedido_origin_id)

    @property
    def modelo_display(self):
        if self.producto_id:
            return self.producto.modelo or self.producto.codigo_articulo
        return (self.modelo_alternativo or '')[:100]

    @property
    def descripcion_display(self):
        if self.producto_id:
            return self.producto.nombre_publico
        return self.modelo_alternativo or 'Equipo Makita'

    @property
    def requiere_mantenimiento(self):
        return self.horas_uso_actuales >= self.horas_proximo_mantenimiento


class Mantenimiento(models.Model):
    TIPO_300H = 'preventivo_300h'
    TIPO_CORRECTIVO = 'correctivo'
    TIPO_GARANTIA = 'garantia'

    TIPO_CHOICES = [
        (TIPO_300H, 'Preventivo 300 Horas'),
        (TIPO_CORRECTIVO, 'Correctivo / Reparación'),
        (TIPO_GARANTIA, 'Garantía Técnica'),
    ]

    ESTADO_INGRESADO = 'ingresado'
    ESTADO_PROCESO = 'en_proceso'
    ESTADO_LISTO = 'listo'
    ESTADO_ENTREGADO = 'entregado'

    ESTADO_CHOICES = [
        (ESTADO_INGRESADO, 'Ingresado (Recepción)'),
        (ESTADO_PROCESO, 'En Proceso de Reparación'),
        (ESTADO_LISTO, 'Listo para Retiro (Completado)'),
        (ESTADO_ENTREGADO, 'Entregado al Cliente'),
    ]

    GARANTIA_BORRADOR = 'borrador'
    GARANTIA_ENVIADO = 'enviado'
    GARANTIA_APROBADO = 'aprobado'
    GARANTIA_RECHAZADO = 'rechazado'
    GARANTIA_CHOICES = [
        (GARANTIA_BORRADOR, 'Borrador'),
        (GARANTIA_ENVIADO, 'Enviado a Lima'),
        (GARANTIA_APROBADO, 'Aprobado MPE'),
        (GARANTIA_RECHAZADO, 'Rechazado MPE'),
    ]

    equipo = models.ForeignKey(
        EquipoRegistrado,
        on_delete=models.CASCADE,
        related_name='mantenimientos',
        verbose_name='Equipo',
    )
    numero_ot = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        verbose_name='Nº OT',
        help_text='Correlativo con prefijo OT- (ej. OT-612).',
    )
    tipo = models.CharField(
        max_length=25,
        choices=TIPO_CHOICES,
        default=TIPO_CORRECTIVO,
        verbose_name='Tipo de Mantenimiento',
    )
    fecha_ingreso = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Ingreso')
    fecha_recepcion = models.DateField(null=True, blank=True, verbose_name='Fecha de recepción')
    fecha_compra = models.DateField(null=True, blank=True, verbose_name='Fecha de compra')
    fecha_entrega_estimada = models.DateTimeField(null=True, blank=True, verbose_name='Fecha Entrega Estimada')
    fecha_entrega_real = models.DateTimeField(null=True, blank=True, verbose_name='Fecha Entrega Real')
    boleta_factura = models.CharField(max_length=80, blank=True, default='', verbose_name='Boleta / Factura')
    distribuidor = models.CharField(max_length=255, blank=True, default='', verbose_name='Distribuidor')
    atencion_sr = models.CharField(max_length=150, blank=True, default='', verbose_name='Att. Sr.')
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mantenimientos_asignados',
        verbose_name='Técnico Asignado',
    )
    diagnostico = models.TextField(blank=True, default='', verbose_name='Diagnóstico / falla (síntoma)')
    causa = models.TextField(blank=True, default='', verbose_name='A causa de qué / informe falla')
    trabajos_realizados = models.TextField(blank=True, verbose_name='Trabajos Realizados')
    informe_tecnico = models.TextField(blank=True, default='', verbose_name='Informe técnico y recomendaciones')
    accesorios = models.TextField(blank=True, default='', verbose_name='Accesorios recibidos')
    observaciones = models.TextField(null=True, blank=True, verbose_name='Observaciones Adicionales')
    repuestos_usados = models.ManyToManyField(
        Producto,
        blank=True,
        related_name='mantenimientos_usados',
        verbose_name='Repuestos Usados',
    )
    costo_mano_obra = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, verbose_name='Costo Mano de Obra'
    )
    costo_repuestos = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, verbose_name='Costo de Repuestos'
    )
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name='Monto Total')
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_INGRESADO,
        verbose_name='Estado de Mantenimiento',
    )
    # Garantía Makita / Lima
    estado_garantia = models.CharField(
        max_length=20,
        choices=GARANTIA_CHOICES,
        default=GARANTIA_BORRADOR,
        verbose_name='Estado garantía Lima',
    )
    categoria_falla = models.CharField(max_length=20, blank=True, default='', verbose_name='Categoría falla')
    autorizacion_mpe = models.CharField(max_length=40, blank=True, default='', verbose_name='Autorización MPE')
    nombre_mpe = models.CharField(max_length=120, blank=True, default='', verbose_name='Nombre MPE')
    comentario_mpe = models.TextField(blank=True, default='', verbose_name='Comentario MPE')
    fecha_aprobacion_mpe = models.DateField(null=True, blank=True, verbose_name='Fecha aprobación / revisión MPE')
    mano_obra_mpe = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Mano de obra MPE'
    )

    class Meta:
        verbose_name = 'Orden de Trabajo'
        verbose_name_plural = 'Órdenes de Trabajo'
        ordering = ['-fecha_ingreso']

    def __str__(self):
        return f'{self.numero_ot or f"OT-{self.id}"} - {self.equipo} ({self.get_estado_display()})'

    @property
    def numero_ot_display(self):
        return self.numero_ot or f'OT-{self.id}'

    @property
    def numero_ot_solo(self):
        """Solo el número (sin OT-) para celdas del Excel."""
        m = re.match(r'^OT-(\d+)$', (self.numero_ot or '').strip(), re.I)
        if m:
            return m.group(1)
        return str(self.id)

    def save(self, *args, **kwargs):
        creating = self.pk is None
        if creating and not self.numero_ot:
            self.numero_ot = ContadorOT.siguiente()
        if not self.fecha_recepcion and creating:
            from django.utils import timezone
            self.fecha_recepcion = timezone.localdate()

        self.total = (self.costo_mano_obra or Decimal('0')) + (self.costo_repuestos or Decimal('0'))

        if self.estado == self.ESTADO_ENTREGADO and not self.fecha_entrega_real:
            from django.utils import timezone
            self.fecha_entrega_real = timezone.now()
            equipo = self.equipo
            equipo.estado = EquipoRegistrado.ESTADO_ACTIVO
            if self.tipo == self.TIPO_300H:
                equipo.horas_proximo_mantenimiento = equipo.horas_uso_actuales + 300
            equipo.save()
        elif self.estado in [self.ESTADO_PROCESO, self.ESTADO_LISTO, self.ESTADO_INGRESADO]:
            equipo = self.equipo
            if equipo.estado != EquipoRegistrado.ESTADO_MANTENIMIENTO:
                equipo.estado = EquipoRegistrado.ESTADO_MANTENIMIENTO
                equipo.save()

        super().save(*args, **kwargs)


class OrdenTrabajoLinea(models.Model):
    """Línea de código/repuesto en la OT o formulario de garantía."""

    mantenimiento = models.ForeignKey(
        Mantenimiento,
        on_delete=models.CASCADE,
        related_name='lineas',
        verbose_name='OT',
    )
    codigo = models.CharField(max_length=50, verbose_name='Código')
    descripcion = models.CharField(max_length=255, blank=True, default='', verbose_name='Descripción')
    cantidad = models.PositiveIntegerField(default=1, verbose_name='Cantidad')
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Línea de OT'
        verbose_name_plural = 'Líneas de OT'
        ordering = ['orden', 'id']

    def __str__(self):
        return f'{self.codigo} x{self.cantidad}'


def registrar_equipos_pedido(pedido):
    from django.utils import timezone
    import datetime

    for detalle in pedido.detalles.all():
        prod = detalle.producto
        if prod.tipo == Producto.TIPO_HERRAMIENTA or prod.familia_sap == 'EQUIPOS':
            registrados = EquipoRegistrado.objects.filter(pedido_origin=pedido, producto=prod).count()
            faltantes = detalle.cantidad - registrados
            if faltantes > 0:
                fecha_compra = timezone.now().date()
                garantia_hasta = fecha_compra + datetime.timedelta(days=365)

                for i in range(faltantes):
                    index = registrados + i + 1
                    sn = f'WEB-{pedido.numero_pedido}-{prod.codigo_articulo}-{index}'

                    base_sn = sn
                    counter = 1
                    while EquipoRegistrado.objects.filter(numero_serie=sn).exists():
                        sn = f'{base_sn}-{counter}'
                        counter += 1

                    EquipoRegistrado.objects.create(
                        cliente=pedido.cliente,
                        pedido_origin=pedido,
                        producto=prod,
                        numero_serie=sn,
                        fecha_compra=fecha_compra,
                        garantia_hasta=garantia_hasta,
                        estado=EquipoRegistrado.ESTADO_ACTIVO,
                        origen=EquipoRegistrado.ORIGEN_NUESTRO,
                    )
