from django.db import models
from django.conf import settings
from django.utils.text import slugify

class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre de Categoría")
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    categoria_padre = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='subcategorias',
        verbose_name="Categoría Padre"
    )
    imagen = models.ImageField(upload_to='categorias/', blank=True, null=True, verbose_name="Imagen de Categoría")

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

    def __str__(self):
        if self.categoria_padre:
            return f"{self.categoria_padre} > {self.nombre}"
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)


class Producto(models.Model):
    TIPO_HERRAMIENTA = 'herramienta'
    TIPO_ACCESORIO = 'accesorio'
    TIPO_REPUESTO = 'repuesto'
    TIPO_SERVICIO = 'servicio'

    TIPO_CHOICES = [
        (TIPO_HERRAMIENTA, 'Herramienta'),
        (TIPO_ACCESORIO, 'Accesorio'),
        (TIPO_REPUESTO, 'Repuesto'),
        (TIPO_SERVICIO, 'Servicio / Varios'),
    ]

    codigo_articulo = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="Código de Artículo (SKU)"
    )
    nombre = models.CharField(max_length=255, verbose_name="Descripción / Nombre")
    nombre_web = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="Nombre para la web",
        help_text="Si está vacío, en la tienda se muestra el nombre importado.",
    )
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción Detallada")
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='productos',
        verbose_name="Categoría Comercial"
    )
    marca = models.CharField(max_length=50, default="Makita", verbose_name="Marca")
    modelo = models.CharField(max_length=100, blank=True, null=True, verbose_name="Modelo")
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default=TIPO_HERRAMIENTA,
        verbose_name="Tipo de Producto"
    )
    
    # Campos Alineados a SAP
    familia_sap = models.CharField(max_length=100, verbose_name="Familia SAP", help_text="Ej: REPUESTOS, ACCESORIOS, EQUIPOS")
    categoria_sap = models.CharField(max_length=100, blank=True, null=True, verbose_name="Categoría SAP")
    status_sap = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Color lista Makita",
        help_text=(
            "Color del Excel Makita (Verde, Amarillo, Rojo, Morado, Azul). "
            "Indica disponibilidad en Lima; es independiente del stock de tienda/web."
        ),
    )

    # Precios (max amplio: Excel Makita a veces trae 9999999 / 999999999)
    # LISTA GENERAL del Excel = sin IGV. Ver apps.tienda.precios
    precio_venta = models.DecimalField(
        decimal_places=2,
        max_digits=12,
        verbose_name="Precio lista (sin IGV)",
        help_text="LISTA GENERAL del Excel Makita. El precio al público sugerido es lista × 1.18.",
    )
    precio_costo = models.DecimalField(
        decimal_places=2,
        max_digits=12,
        default=0.00,
        verbose_name="Precio de compra / costo",
        help_text="Costo de adquisición. No se importa del Excel de lista.",
    )
    # Precios tienda web (promoción) — ya con IGV al cliente
    precio_tachado = models.DecimalField(
        decimal_places=2,
        max_digits=12,
        blank=True,
        null=True,
        verbose_name="Precio tachado (web)",
        help_text="Precio anterior mostrado tachado (con IGV). Si se llena junto al precio web, se marca como promoción.",
    )
    precio_web = models.DecimalField(
        decimal_places=2,
        max_digits=12,
        blank=True,
        null=True,
        verbose_name="Precio final (web)",
        help_text="Precio de venta en la tienda web (con IGV). Si está vacío se usa lista × 1.18.",
    )

    # Inventario
    stock = models.IntegerField(
        default=0,
        verbose_name="Stock en tienda (POS)",
        help_text="Unidades disponibles para venta presencial.",
    )
    stock_web = models.IntegerField(
        default=0,
        verbose_name="Stock en web",
        help_text="Unidades asignadas / disponibles para la tienda online.",
    )
    stock_minimo = models.IntegerField(default=5, verbose_name="Stock Mínimo Alerta")

    # Atributos Físicos/Técnicos
    imagen_principal = models.ImageField(upload_to='productos/', blank=True, null=True, verbose_name="Imagen Principal")
    posicion_despiece = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Posición en despiece",
        help_text="Número o código de posición en el diagrama de desarme interno (Ej. Pos. 42).",
    )
    peso = models.DecimalField(
        decimal_places=3,
        max_digits=6,
        blank=True,
        null=True,
        verbose_name="Peso (kg)"
    )
    voltaje = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Voltaje",
        help_text="Ej: 18V LXT, 40V Max, 220V"
    )
    
    activo = models.BooleanField(
        default=True,
        verbose_name="Activo (POS / interno)",
        help_text="Si está activo puede usarse en POS e inventario interno.",
    )
    mostrar_en_web = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Mostrar en tienda web",
        help_text="Solo los productos marcados aquí aparecen en el catálogo público.",
    )
    venta_bloqueada = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Venta bloqueada",
        help_text="Se activa durante importaciones de catálogo que afectan este producto.",
    )
    mostrar_ficha_tecnica = models.BooleanField(
        default=False,
        verbose_name="Mostrar ficha técnica en web",
        help_text="Si está activo, se muestra el recuadro de atributos nombre/valor en la ficha pública.",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['nombre']

    def __str__(self):
        return f"[{self.codigo_articulo}] {self.nombre}"

    @property
    def codigo_display(self) -> str:
        """Si el código es autogenerado (SRV-..., PRD-...) o vacío, retorna '—'."""
        if not self.codigo_articulo:
            return '—'
        cod = str(self.codigo_articulo).strip()
        if cod.startswith('SRV-') or cod.startswith('PRD-'):
            return '—'
        return cod

    @property
    def nombre_publico(self):
        """Nombre mostrado en web (nombre_web o el importado)."""
        return (self.nombre_web or '').strip() or self.nombre

    @property
    def color_lista(self):
        """Color del Excel Makita (STATUS), normalizado."""
        return (self.status_sap or '').strip()

    @property
    def color_lista_key(self):
        return self.color_lista.casefold()

    # Etiquetas STATUS STOCK Lima (independiente del stock local).
    _LIMA_LABELS = {
        'rojo': 'Agotado',
        'morado': '1–10 und',
        'amarillo': '11–50 und',
        'azul': '51–100 und',
        'verde': '101 a más',
    }

    @property
    def disponibilidad_lima_label(self):
        """Texto corto del badge de color lista / stock Lima."""
        key = self.color_lista_key
        if not key:
            return ''
        return self._LIMA_LABELS.get(key, self.color_lista)

    @property
    def disponibilidad_lima_css(self):
        """Clase CSS del badge (lima-verde, lima-rojo, …)."""
        key = self.color_lista_key
        if key in self._LIMA_LABELS:
            return f'lima-{key}'
        if key:
            return 'lima-otro'
        return ''

    @property
    def precio_lista(self):
        """Alias: LISTA GENERAL sin IGV (Excel Makita)."""
        return self.precio_venta

    @property
    def precio_lista_con_igv(self):
        """Precio sugerido al público: lista × 1.18."""
        from apps.tienda.precios import con_igv
        return con_igv(self.precio_venta)

    @property
    def en_promocion(self):
        """Hay promoción si están ambos precios web y el tachado es mayor al final."""
        if self.precio_tachado is None or self.precio_web is None:
            return False
        return self.precio_tachado > self.precio_web

    @property
    def precio_publico(self):
        """Precio que paga el cliente en la web (con IGV)."""
        if self.precio_web is not None:
            return self.precio_web
        return self.precio_lista_con_igv

    def save(self, *args, **kwargs):
        if self.nombre:
            self.nombre = self.nombre.strip().upper()
        if not self.slug:
            # Combinamos nombre y código para evitar colisiones
            self.slug = slugify(f"{self.nombre}-{self.codigo_articulo}")
        super().save(*args, **kwargs)

    @property
    def imagen_destacada_url(self):
        """URL de la imagen principal/primordial del producto (para web y cotizaciones)."""
        img_galeria_principal = self.imagenes.filter(es_principal=True).first()
        if img_galeria_principal and img_galeria_principal.imagen:
            try:
                return img_galeria_principal.imagen.url
            except ValueError:
                pass
        if self.imagen_principal:
            try:
                return self.imagen_principal.url
            except ValueError:
                pass
        primera_galeria = self.imagenes.first()
        if primera_galeria and primera_galeria.imagen:
            try:
                return primera_galeria.imagen.url
            except ValueError:
                pass
        return None

    def imagenes_galeria(self):
        """Lista de URLs únicas para galería web (principal + extras, sin duplicados)."""
        from pathlib import Path

        urls = []
        seen = set()

        def _add(field):
            if not field:
                return
            try:
                url = field.url
            except ValueError:
                return
            if not url:
                return
            path = url.split('?', 1)[0]
            name = Path(path).name.lower()
            if path in seen or name in seen:
                return
            seen.add(path)
            seen.add(name)
            urls.append(url)

        _add(self.imagen_principal)
        for im in self.imagenes.order_by('-es_principal', 'orden', 'id'):
            _add(im.imagen)
        return urls


class ProductoAtributo(models.Model):
    """Fila de ficha técnica: nombre + valor (ej. RPM: 11000)."""

    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='atributos',
        verbose_name='Producto',
    )
    nombre = models.CharField(max_length=120, verbose_name='Nombre')
    valor = models.CharField(max_length=255, verbose_name='Valor')
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Atributo de ficha técnica'
        verbose_name_plural = 'Atributos de ficha técnica'
        ordering = ['orden', 'id']

    def __str__(self):
        return f'{self.nombre}: {self.valor}'


class ProductoImagen(models.Model):
    """Imagen de galería (se guarda en WebP al subir)."""

    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='imagenes',
        verbose_name='Producto',
    )
    imagen = models.ImageField(upload_to='productos/galeria/%Y/%m/', verbose_name='Imagen')
    orden = models.PositiveIntegerField(default=0)
    es_principal = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Imagen de producto'
        verbose_name_plural = 'Imágenes de producto'
        ordering = ['-es_principal', 'orden', 'id']

    def __str__(self):
        return f'{self.producto.codigo_articulo} · img #{self.id}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.es_principal:
            ProductoImagen.objects.filter(producto=self.producto).exclude(id=self.id).update(es_principal=False)



class ImportacionCatalogo(models.Model):
    TIPO_REPUESTOS = 'repuestos'
    TIPO_ACCESORIOS = 'accesorios_equipos'
    TIPO_AUTO = 'auto'

    TIPO_CHOICES = [
        (TIPO_REPUESTOS, 'Repuestos'),
        (TIPO_ACCESORIOS, 'Equipos y Accesorios'),
        (TIPO_AUTO, 'Detectado automáticamente'),
    ]

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_PROCESANDO = 'procesando'
    ESTADO_COMPLETADA = 'completada'
    ESTADO_ERROR = 'error'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_PROCESANDO, 'Procesando'),
        (ESTADO_COMPLETADA, 'Completada'),
        (ESTADO_ERROR, 'Error'),
    ]

    archivo_nombre = models.CharField(max_length=255, verbose_name="Archivo")
    archivo = models.FileField(
        upload_to='importaciones/%Y/%m/',
        blank=True,
        null=True,
        verbose_name="Archivo guardado",
        help_text=(
            "Solo se conserva si la importación falla o tiene errores de fila. "
            "Tras un éxito sin errores se elimina del disco (los cambios quedan en el log)."
        ),
    )
    tipo_archivo = models.CharField(max_length=30, choices=TIPO_CHOICES, default=TIPO_AUTO)
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE,
        db_index=True,
    )
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")
    fecha_fin = models.DateTimeField(blank=True, null=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='importaciones_catalogo',
    )
    total_filas = models.PositiveIntegerField(default=0)
    total_procesadas = models.PositiveIntegerField(default=0)
    total_nuevos = models.PositiveIntegerField(default=0)
    total_actualizados = models.PositiveIntegerField(default=0)
    total_sin_cambio = models.PositiveIntegerField(default=0)
    total_errores = models.PositiveIntegerField(default=0)
    mensaje_error = models.TextField(blank=True, default='')
    notas = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = "Importación de catálogo"
        verbose_name_plural = "Importaciones de catálogo"
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.archivo_nombre} · {self.fecha:%d/%m/%Y %H:%M}"

    @property
    def progreso_pct(self):
        if not self.total_filas:
            return 0
        return min(100, int(100 * self.total_procesadas / self.total_filas))


class LogCambioImportacion(models.Model):
    TIPO_NUEVO = 'nuevo'
    TIPO_PRECIO_SUBE = 'precio_sube'
    TIPO_PRECIO_BAJA = 'precio_baja'
    TIPO_NOMBRE = 'nombre'
    TIPO_CODIGO = 'codigo'
    TIPO_STATUS = 'status'
    TIPO_FAMILIA = 'familia'
    TIPO_REACTIVADO = 'reactivado'
    TIPO_ERROR = 'error'

    TIPO_CHOICES = [
        (TIPO_NUEVO, 'Producto nuevo'),
        (TIPO_PRECIO_SUBE, 'Precio subió'),
        (TIPO_PRECIO_BAJA, 'Precio bajó'),
        (TIPO_NOMBRE, 'Nombre cambió'),
        (TIPO_CODIGO, 'Código cambió'),
        (TIPO_STATUS, 'Color lista (Status)'),
        (TIPO_FAMILIA, 'Familia SAP'),
        (TIPO_REACTIVADO, 'Reactivado'),
        (TIPO_ERROR, 'Error / fila omitida'),
    ]

    importacion = models.ForeignKey(
        ImportacionCatalogo,
        on_delete=models.CASCADE,
        related_name='cambios',
    )
    codigo_articulo = models.CharField(max_length=50, db_index=True)
    tipo_cambio = models.CharField(max_length=20, choices=TIPO_CHOICES)
    campo = models.CharField(max_length=50, blank=True, default='')
    valor_anterior = models.TextField(blank=True, default='')
    valor_nuevo = models.TextField(blank=True, default='')
    detalle = models.TextField(blank=True, default='', verbose_name='Motivo / detalle')

    class Meta:
        verbose_name = "Log de cambio de importación"
        verbose_name_plural = "Logs de cambios de importación"
        ordering = ['id']

    def __str__(self):
        return f"{self.codigo_articulo} · {self.get_tipo_cambio_display()}"


class StockSede(models.Model):
    """Stock de un producto en una sede (solo si la sede NO comparte inventario)."""

    producto = models.ForeignKey(
        Producto, on_delete=models.CASCADE, related_name='stocks_sede',
    )
    sede = models.ForeignKey(
        'sistema.Sede', on_delete=models.CASCADE, related_name='stocks',
    )
    cantidad = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Stock por sede'
        verbose_name_plural = 'Stocks por sede'
        unique_together = [('producto', 'sede')]

    def __str__(self):
        return f'{self.producto.codigo_articulo} @ {self.sede.codigo}: {self.cantidad}'
