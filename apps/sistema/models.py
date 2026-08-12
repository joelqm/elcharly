from django.db import models
from django.conf import settings


class Empresa(models.Model):
    """Empresa emisora (STA El Charly Makita)."""

    nombre = models.CharField(max_length=150, default='STA El Charly Makita')
    nombre_corto = models.CharField(max_length=80, default='El Charly')
    ruc = models.CharField(max_length=11, blank=True, default='')
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'

    def __str__(self):
        return self.nombre_corto or self.nombre


class Sede(models.Model):
    """Local operativo: tienda, taller, etc."""

    TIPO_TIENDA = 'tienda'
    TIPO_TALLER = 'taller'
    TIPO_OTRO = 'otro'
    TIPO_CHOICES = [
        (TIPO_TIENDA, 'Tienda'),
        (TIPO_TALLER, 'Taller'),
        (TIPO_OTRO, 'Otro'),
    ]

    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name='sedes',
    )
    codigo = models.SlugField(max_length=30, unique=True)
    nombre = models.CharField(max_length=120)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_TIENDA)
    direccion = models.CharField(max_length=255, blank=True, default='')
    telefono = models.CharField(max_length=40, blank=True, default='')
    whatsapp = models.CharField(
        max_length=20, blank=True, default='',
        help_text='Solo dígitos con código país, ej. 51960160842',
    )
    yape_numero = models.CharField(max_length=20, blank=True, default='')
    yape_titular = models.CharField(max_length=120, blank=True, default='')
    yape_qr = models.ImageField(upload_to='sedes/yape/', blank=True, null=True)
    # Si True: usa Producto.stock global. Si False: stock por sede (StockSede).
    compartir_productos = models.BooleanField(
        default=True,
        verbose_name='Compartir productos/stock con otras sedes',
        help_text='Desactiva para que esta sede maneje stock propio.',
    )
    activa = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Sede'
        verbose_name_plural = 'Sedes'
        ordering = ['orden', 'nombre']

    def __str__(self):
        return f'{self.nombre} ({self.get_tipo_display()})'


class LogActividad(models.Model):
    """Registro de acciones importantes y navegación del staff interno."""

    TIPO_LOGIN = 'login'
    TIPO_LOGOUT = 'logout'
    TIPO_NAV = 'navegacion'
    TIPO_VENTA = 'venta'
    TIPO_INVENTARIO = 'inventario'
    TIPO_WEB = 'productos_web'
    TIPO_IMPORT = 'importacion'
    TIPO_SISTEMA = 'sistema'
    TIPO_OTRO = 'otro'

    TIPO_CHOICES = [
        (TIPO_LOGIN, 'Inicio de sesión'),
        (TIPO_LOGOUT, 'Cierre de sesión'),
        (TIPO_NAV, 'Navegación'),
        (TIPO_VENTA, 'Venta / POS'),
        (TIPO_INVENTARIO, 'Inventario'),
        (TIPO_WEB, 'Productos web'),
        (TIPO_IMPORT, 'Importación'),
        (TIPO_SISTEMA, 'Sistema'),
        (TIPO_OTRO, 'Otro'),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs_actividad',
    )
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default=TIPO_OTRO, db_index=True)
    accion = models.CharField(max_length=120, verbose_name='Acción')
    detalle = models.TextField(blank=True, default='')
    ruta = models.CharField(max_length=255, blank=True, default='')
    metodo = models.CharField(max_length=10, blank=True, default='')
    ip = models.GenericIPAddressField(blank=True, null=True)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Log de actividad'
        verbose_name_plural = 'Logs de actividad'
        ordering = ['-fecha']

    def __str__(self):
        who = self.usuario.username if self.usuario_id else 'anónimo'
        return f'{self.fecha:%d/%m %H:%M} · {who} · {self.accion}'
