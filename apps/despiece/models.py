from django.db import models
from apps.tienda.models import Producto


class DespieceEquipo(models.Model):
    modelo = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="Modelo del Equipo",
        help_text="Ej: GA4590, DHP484, HR2470"
    )
    nombre_equipo = models.CharField(
        max_length=255,
        verbose_name="Descripción / Nombre del Equipo",
        help_text="Ej: Esmeriladora Angular 115mm"
    )
    archivo_pdf = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="Ruta del PDF de Origen"
    )
    imagen_diagrama = models.ImageField(
        upload_to='despieces/diagramas/',
        blank=True,
        null=True,
        verbose_name="Imagen Renderizada del Diagrama Explosionado"
    )
    pdf = models.FileField(
        upload_to='despieces/pdfs/',
        blank=True,
        null=True,
        verbose_name='PDF original Makita',
    )
    total_partes = models.PositiveIntegerField(default=0, verbose_name="Total de Partes")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Despiece de Equipo"
        verbose_name_plural = "Despieces de Equipos"
        ordering = ['modelo']

    def __str__(self):
        return f"{self.modelo} - {self.nombre_equipo}"


class DespieceItem(models.Model):
    despiece = models.ForeignKey(
        DespieceEquipo,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Despiece de Equipo"
    )
    posicion = models.CharField(
        max_length=30,
        db_index=True,
        verbose_name="Posición en Diagrama (Art. No.)",
        help_text="Ej: 016, 017, 068-1"
    )
    codigo_articulo = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name="Número de Parte / SKU",
        help_text="Ej: 511A48-8, 681656-4"
    )
    descripcion = models.CharField(
        max_length=255,
        verbose_name="Descripción del Repuesto / Parte"
    )
    cantidad = models.PositiveIntegerField(default=1, verbose_name="Cantidad requerida por equipo")
    producto = models.ForeignKey(
        Producto,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='despieces_asociados',
        verbose_name="Producto en Catálogo Sistema"
    )

    class Meta:
        verbose_name = "Ítem de Despiece"
        verbose_name_plural = "Ítems de Despieces"
        ordering = ['id']

    def __str__(self):
        return f"[{self.despiece.modelo}] Pos {self.posicion}: {self.codigo_articulo} - {self.descripcion}"


class DespiecePagina(models.Model):
    """Una o más páginas del diagrama explosionado (como MSI 1/2, 2/2)."""

    despiece = models.ForeignKey(
        DespieceEquipo,
        on_delete=models.CASCADE,
        related_name='paginas',
        verbose_name='Despiece',
    )
    numero = models.PositiveSmallIntegerField(default=1, verbose_name='Nº de página')
    imagen = models.ImageField(
        upload_to='despieces/diagramas/',
        verbose_name='Imagen de la página',
    )

    class Meta:
        verbose_name = 'Página de despiece'
        verbose_name_plural = 'Páginas de despiece'
        ordering = ['numero']
        unique_together = [('despiece', 'numero')]

    def __str__(self):
        return f'{self.despiece.modelo} · pág. {self.numero}'


class DespieceHotspot(models.Model):
    """
    Zona clicable sobre el diagrama (estilo Makita MSI).
    Coordenadas en % del ancho/alto de la imagen (0–100) para que escalen con zoom.
    """

    despiece = models.ForeignKey(
        DespieceEquipo,
        on_delete=models.CASCADE,
        related_name='hotspots',
        verbose_name='Despiece',
    )
    pagina = models.PositiveSmallIntegerField(default=1, db_index=True, verbose_name='Página')
    posicion = models.CharField(
        max_length=30,
        db_index=True,
        verbose_name='Posición (Art. No.)',
        help_text='Debe coincidir con DespieceItem.posicion (ej. 88 o 016).',
    )
    cx = models.FloatField(verbose_name='Centro X %')
    cy = models.FloatField(verbose_name='Centro Y %')
    r = models.FloatField(default=2.2, verbose_name='Radio % del ancho')
    puntos = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Silueta (puntos %)',
        help_text='Polígono [{x, y}, …] en porcentaje del diagrama. Vacío = solo pin del número.',
    )

    class Meta:
        verbose_name = 'Hotspot de despiece'
        verbose_name_plural = 'Hotspots de despiece'
        ordering = ['pagina', 'posicion']

    def __str__(self):
        return f'{self.despiece.modelo} p{self.pagina} · pos {self.posicion}'
