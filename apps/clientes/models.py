from django.db import models

class Cliente(models.Model):
    TIPO_PERSONA = 'persona'
    TIPO_EMPRESA = 'empresa'

    TIPO_CHOICES = [
        (TIPO_PERSONA, 'Persona Natural'),
        (TIPO_EMPRESA, 'Empresa / Jurídica'),
    ]

    CANAL_WEB = 'web'
    CANAL_POS = 'pos'
    CANAL_REFERIDO = 'referido'

    CANAL_CHOICES = [
        (CANAL_WEB, 'Tienda Web'),
        (CANAL_POS, 'Tienda Física / POS'),
        (CANAL_REFERIDO, 'Referido / Otro'),
    ]

    nombre_completo = models.CharField(max_length=255, verbose_name="Nombre Completo o Razón Social")
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default=TIPO_PERSONA,
        verbose_name="Tipo de Cliente"
    )
    dni_ruc = models.CharField(max_length=20, unique=True, verbose_name="DNI o RUC")
    telefono = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono")
    correo = models.EmailField(blank=True, null=True, verbose_name="Correo Electrónico")
    direccion = models.CharField(max_length=255, blank=True, null=True, verbose_name="Dirección")
    ciudad = models.CharField(max_length=100, default="Arequipa", verbose_name="Ciudad")
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Registro")
    canal_origen = models.CharField(
        max_length=20,
        choices=CANAL_CHOICES,
        default=CANAL_WEB,
        verbose_name="Canal de Origen"
    )
    ETIQUETA_NUEVO = 'nuevo'
    ETIQUETA_FRECUENTE = 'frecuente'
    ETIQUETA_VIP = 'vip'
    ETIQUETA_EMPRESA = 'empresa'
    ETIQUETA_INACTIVO = 'inactivo'

    ETIQUETA_CHOICES = [
        (ETIQUETA_NUEVO, 'Cliente Nuevo'),
        (ETIQUETA_FRECUENTE, 'Cliente Frecuente'),
        (ETIQUETA_VIP, 'Cliente VIP'),
        (ETIQUETA_EMPRESA, 'Empresa'),
        (ETIQUETA_INACTIVO, 'Cliente Inactivo'),
    ]

    etiqueta = models.CharField(
        max_length=20,
        choices=ETIQUETA_CHOICES,
        default=ETIQUETA_NUEVO,
        verbose_name="Clasificación / Etiqueta"
    )
    notas = models.TextField(blank=True, null=True, verbose_name="Notas Internas")

    @property
    def total_comprado(self):
        from apps.pedidos.models import Pedido
        from django.db.models import Sum
        total = self.pedidos.filter(
            estado__in=Pedido.ESTADOS_CONCRETADOS,
        ).aggregate(total_sum=Sum('total'))['total_sum']
        return total or 0

    @property
    def numero_pedidos(self):
        from apps.pedidos.models import Pedido
        return self.pedidos.filter(estado__in=Pedido.ESTADOS_CONCRETADOS).count()

    @property
    def etiqueta_sugerida(self):
        if self.tipo == self.TIPO_EMPRESA:
            return 'Empresa'
        count = self.numero_pedidos
        total = self.total_comprado
        if total >= 5000 or count >= 10:
            return 'VIP'
        elif count >= 3:
            return 'Cliente Frecuente'
        return 'Cliente Nuevo'
        
    class Meta:
        verbose_name = "Cliente (CRM)"
        verbose_name_plural = "Clientes (CRM)"
        ordering = ['nombre_completo']

    def __str__(self):
        return f"{self.nombre_completo} ({self.dni_ruc})"
