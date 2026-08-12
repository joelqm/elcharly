from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Empresa, Sede, LogActividad


class SedeInline(admin.TabularInline):
    model = Sede
    extra = 0
    fields = (
        'codigo', 'nombre', 'tipo', 'compartir_productos',
        'activa', 'orden', 'yape_numero', 'whatsapp',
    )


@admin.register(Empresa)
class EmpresaAdmin(ModelAdmin):
    list_display = ('nombre_corto', 'ruc', 'activa')
    inlines = [SedeInline]


@admin.register(Sede)
class SedeAdmin(ModelAdmin):
    list_display = (
        'nombre', 'codigo', 'tipo', 'empresa',
        'compartir_productos', 'activa', 'orden',
    )
    list_filter = ('tipo', 'activa', 'compartir_productos', 'empresa')
    search_fields = ('nombre', 'codigo', 'direccion')
    fieldsets = (
        (None, {'fields': ('empresa', 'codigo', 'nombre', 'tipo', 'orden', 'activa')}),
        ('Ubicación', {'fields': ('direccion', 'telefono', 'whatsapp')}),
        ('Yape', {'fields': ('yape_numero', 'yape_titular', 'yape_qr')}),
        ('Inventario', {
            'fields': ('compartir_productos',),
            'description': (
                'Si está activo, usa el stock global del producto. '
                'Si lo desactivas, el stock de esta sede se maneja aparte (StockSede).'
            ),
        }),
    )


@admin.register(LogActividad)
class LogActividadAdmin(ModelAdmin):
    list_display = ('fecha', 'usuario', 'tipo', 'accion', 'ruta')
    list_filter = ('tipo',)
    search_fields = ('accion', 'detalle', 'usuario__username')
    readonly_fields = ('usuario', 'tipo', 'accion', 'detalle', 'ruta', 'metodo', 'ip', 'fecha')
