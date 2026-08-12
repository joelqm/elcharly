from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import MovimientoInventario

@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(ModelAdmin):
    list_display = ('producto', 'tipo_badge', 'cantidad', 'get_motivo_display', 'fecha', 'usuario')
    list_filter = ('tipo', 'motivo', 'fecha', 'usuario')
    search_fields = ('producto__codigo_articulo', 'producto__nombre', 'usuario__username')
    ordering = ('-fecha',)
    
    # Todos los campos son de solo lectura al ver un detalle existente para evitar alteración de historial
    def get_readonly_fields(self, request, obj=None):
        if obj: # Editando objeto existente
            return [f.name for f in self.model._meta.fields]
        return ('usuario',) # Al crear, el usuario se auto-asigna y es de solo lectura

    def save_model(self, request, obj, form, change):
        if not change:
            obj.usuario = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False # No se permite eliminar movimientos de inventario

    def tipo_badge(self, obj):
        from django.utils.html import format_html
        if obj.tipo == MovimientoInventario.TIPO_ENTRADA:
            return format_html(
                '<span class="bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400 px-2 py-0.5 rounded text-xs font-semibold inline-flex items-center gap-1"><i class="fa-solid fa-arrow-turn-up"></i> Entrada</span>'
            )
        return format_html(
            '<span class="bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400 px-2 py-0.5 rounded text-xs font-semibold inline-flex items-center gap-1"><i class="fa-solid fa-arrow-turn-down"></i> Salida</span>'
        )
    tipo_badge.short_description = "Tipo"
