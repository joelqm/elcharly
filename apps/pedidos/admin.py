from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import Pedido, DetallePedido, PedidoWeb, VentaTienda, PedidoDesdeCotizacion


class DetallePedidoInline(TabularInline):
    model = DetallePedido
    extra = 0
    readonly_fields = ('subtotal',)


class PedidoBaseAdmin(ModelAdmin):
    list_display = ('numero_pedido', 'cliente', 'estado_badge', 'es_historica', 'fecha_pedido', 'total', 'atendido_por')
    list_filter = ('estado', 'es_historica', 'fecha_pedido')
    search_fields = ('numero_pedido', 'cliente__nombre_completo', 'cliente__dni_ruc')
    inlines = [DetallePedidoInline]
    ordering = ('-fecha_pedido',)
    date_hierarchy = 'fecha_pedido'

    fieldsets = (
        ('Información general', {
            'fields': ('numero_pedido', 'cliente', 'canal', 'estado', 'fecha_pedido', 'es_historica', 'atendido_por', 'caja_sesion')
        }),
        ('Totales', {
            'fields': ('subtotal', 'igv', 'total')
        }),
        ('Detalles y notas', {
            'fields': ('direccion_envio', 'notas')
        }),
    )
    readonly_fields = ('numero_pedido',)

    def estado_badge(self, obj):
        colors = {
            Pedido.ESTADO_PENDIENTE: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
            Pedido.ESTADO_PAGADO: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
            Pedido.ESTADO_ENVIADO: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400",
            Pedido.ESTADO_ENTREGADO: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
            Pedido.ESTADO_CANCELADO: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
        }
        color_class = colors.get(obj.estado, "bg-gray-100 text-gray-700")
        return format_html(
            '<span class="{} px-2 py-0.5 rounded text-xs font-semibold">{}</span>',
            color_class,
            obj.get_estado_display()
        )
    estado_badge.short_description = "Estado"


@admin.register(PedidoWeb)
class PedidoWebAdmin(PedidoBaseAdmin):
    """Solo pedidos del canal web."""

    def get_queryset(self, request):
        return super().get_queryset(request).filter(canal=Pedido.CANAL_WEB)

    def get_changeform_initial_data(self, request):
        return {'canal': Pedido.CANAL_WEB}

    def save_model(self, request, obj, form, change):
        obj.canal = Pedido.CANAL_WEB
        super().save_model(request, obj, form, change)


@admin.register(VentaTienda)
class VentaTiendaAdmin(PedidoBaseAdmin):
    """Solo ventas de tienda / POS."""

    list_display = (
        'numero_pedido', 'cliente', 'estado_badge', 'fecha_pedido',
        'total', 'caja_sesion', 'atendido_por'
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(canal=Pedido.CANAL_POS)

    def get_changeform_initial_data(self, request):
        return {'canal': Pedido.CANAL_POS}

    def save_model(self, request, obj, form, change):
        obj.canal = Pedido.CANAL_POS
        if not obj.atendido_por_id:
            obj.atendido_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(PedidoDesdeCotizacion)
class PedidoDesdeCotizacionAdmin(PedidoBaseAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(canal=Pedido.CANAL_COTIZACION)

    def get_changeform_initial_data(self, request):
        return {'canal': Pedido.CANAL_COTIZACION}

    def save_model(self, request, obj, form, change):
        obj.canal = Pedido.CANAL_COTIZACION
        super().save_model(request, obj, form, change)
