from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Pago

@admin.register(Pago)
class PagoAdmin(ModelAdmin):
    list_display = ('id', 'pedido', 'metodo', 'monto', 'estado_badge', 'fecha_pago', 'referencia_externa')
    list_filter = ('metodo', 'estado', 'fecha_pago')
    search_fields = ('pedido__numero_pedido', 'referencia_externa')
    ordering = ('-fecha_pago',)

    def estado_badge(self, obj):
        from django.utils.html import format_html
        
        colors = {
            Pago.ESTADO_PENDIENTE: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
            Pago.ESTADO_APROBADO: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
            Pago.ESTADO_RECHAZADO: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
            Pago.ESTADO_REEMBOLSADO: "bg-gray-100 text-gray-700",
        }
        
        color_class = colors.get(obj.estado, "bg-gray-100 text-gray-700")
        return format_html(
            '<span class="{} px-2 py-0.5 rounded text-xs font-semibold">{}</span>',
            color_class,
            obj.get_estado_display()
        )
    estado_badge.short_description = "Estado"
