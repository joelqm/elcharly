from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import (
    Categoria, Producto, ProductoAtributo, ProductoImagen,
    ImportacionCatalogo, LogCambioImportacion,
)


@admin.register(Categoria)
class CategoriaAdmin(ModelAdmin):
    list_display = ('nombre', 'slug', 'categoria_padre', 'total_productos')
    prepopulated_fields = {'slug': ('nombre',)}
    search_fields = ('nombre',)
    list_filter = ('categoria_padre',)

    def total_productos(self, obj):
        return obj.productos.count()
    total_productos.short_description = "Total Productos"


class ProductoAtributoInline(TabularInline):
    model = ProductoAtributo
    extra = 2


class ProductoImagenInline(TabularInline):
    model = ProductoImagen
    extra = 1


@admin.register(Producto)
class ProductoAdmin(ModelAdmin):
    list_display = (
        'codigo_articulo',
        'nombre',
        'nombre_web',
        'familia_sap',
        'tipo',
        'status_sap',
        'modelo',
        'precio_venta',
        'stock_status',
        'activo',
        'mostrar_en_web',
    )
    list_filter = ('tipo', 'familia_sap', 'categoria', 'activo', 'mostrar_en_web', 'voltaje')
    list_editable = ('mostrar_en_web',)
    search_fields = ('codigo_articulo', 'nombre', 'nombre_web', 'modelo', 'categoria_sap')
    prepopulated_fields = {'slug': ('nombre', 'codigo_articulo')}
    inlines = [ProductoAtributoInline, ProductoImagenInline]

    fieldsets = (
        ('Identificación SAP', {
            'fields': (
                'codigo_articulo', 'nombre', 'nombre_web', 'slug', 'modelo',
                'activo', 'mostrar_en_web', 'mostrar_ficha_tecnica',
            )
        }),
        ('Clasificación SAP', {
            'fields': ('familia_sap', 'categoria_sap', 'status_sap', 'categoria', 'tipo')
        }),
        ('Precios', {
            'fields': ('precio_venta', 'precio_costo', 'precio_tachado', 'precio_web')
        }),
        ('Inventario', {
            'fields': ('stock', 'stock_web', 'stock_minimo', 'venta_bloqueada')
        }),
        ('Especificaciones Técnicas', {
            'fields': ('peso', 'voltaje', 'imagen_principal', 'descripcion')
        }),
    )

    def stock_status(self, obj):
        if obj.stock <= obj.stock_minimo:
            return format_html(
                '<span class="bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400 px-2 py-1 rounded text-xs font-semibold inline-flex items-center gap-1"><i class="fa-solid fa-triangle-exclamation"></i> {} (Crítico)</span>',
                obj.stock
            )
        return format_html(
            '<span class="bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400 px-2 py-1 rounded text-xs font-semibold inline-flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> {}</span>',
            obj.stock
        )
    stock_status.short_description = "Stock"


class LogCambioImportacionInline(TabularInline):
    model = LogCambioImportacion
    extra = 0
    readonly_fields = (
        'codigo_articulo', 'tipo_cambio', 'campo',
        'valor_anterior', 'valor_nuevo', 'detalle',
    )
    can_delete = False
    max_num = 0


@admin.register(ImportacionCatalogo)
class ImportacionCatalogoAdmin(ModelAdmin):
    list_display = (
        'fecha', 'archivo_nombre', 'tipo_archivo',
        'total_filas', 'total_nuevos', 'total_actualizados',
        'total_sin_cambio', 'usuario',
    )
    list_filter = ('tipo_archivo', 'fecha')
    search_fields = ('archivo_nombre',)
    readonly_fields = (
        'archivo_nombre', 'tipo_archivo', 'fecha', 'usuario',
        'total_filas', 'total_nuevos', 'total_actualizados',
        'total_sin_cambio', 'notas',
    )
    inlines = [LogCambioImportacionInline]
    ordering = ('-fecha',)


@admin.register(LogCambioImportacion)
class LogCambioImportacionAdmin(ModelAdmin):
    list_display = (
        'importacion', 'codigo_articulo', 'tipo_cambio',
        'campo', 'valor_anterior', 'valor_nuevo',
    )
    list_filter = ('tipo_cambio', 'importacion')
    search_fields = ('codigo_articulo', 'valor_anterior', 'valor_nuevo')
    readonly_fields = (
        'importacion', 'codigo_articulo', 'tipo_cambio',
        'campo', 'valor_anterior', 'valor_nuevo', 'detalle',
    )
