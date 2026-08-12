from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import Cotizacion, DetalleCotizacion

class DetalleCotizacionInline(TabularInline):
    model = DetalleCotizacion
    extra = 1
    fields = (
        'repuesto', 'codigo_articulo', 'descripcion', 'cantidad',
        'precio_costo', 'precio_lista', 'precio_unitario', 'subtotal',
    )
    readonly_fields = ('subtotal',)

@admin.register(Cotizacion)
class CotizacionAdmin(ModelAdmin):
    list_display = ('numero', 'get_cliente_display', 'estado', 'total', 'fecha_creacion', 'fecha_vencimiento')
    list_filter = ('estado', 'fecha_creacion', 'fecha_vencimiento')
    search_fields = ('numero', 'cliente__nombre_completo', 'nombre_cliente_temporal')
    inlines = [DetalleCotizacionInline]
    readonly_fields = ('numero', 'subtotal', 'igv', 'total')
    
    fieldsets = (
        ('Información General', {
            'fields': ('numero', 'estado', 'fecha_vencimiento', 'creado_por')
        }),
        ('Cliente CRM', {
            'fields': ('cliente',)
        }),
        ('Cliente Temporal (Anónimo)', {
            'fields': (
                'nombre_cliente_temporal', 'dni_ruc_cliente_temporal',
                'correo_cliente_temporal', 'telefono_cliente_temporal',
                'direccion_cliente_temporal',
            )
        }),
        ('Totales', {
            'fields': ('subtotal', 'igv', 'total')
        }),
        ('Observaciones PDF / Notas', {
            'fields': ('observaciones', 'notas')
        }),
    )

    def get_cliente_display(self, obj):
        if obj.cliente:
            return obj.cliente.nombre_completo
        return obj.nombre_cliente_temporal or "Cliente Anónimo"
    get_cliente_display.short_description = "Cliente"

    def has_delete_permission(self, request, obj=None):
        return False
