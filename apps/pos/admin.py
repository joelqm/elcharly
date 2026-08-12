from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from unfold.admin import ModelAdmin
from .models import CajaSesion, TicketPOS, MovimientoCaja

@admin.register(CajaSesion)
class CajaSesionAdmin(ModelAdmin):
    list_display = (
        'id',
        'cajero',
        'fecha_apertura',
        'fecha_cierre',
        'monto_apertura',
        'monto_cierre',
        'estado_badge',
        'exportar_cierre_link'
    )
    list_filter = ('estado', 'fecha_apertura', 'cajero')
    search_fields = ('cajero__username', 'observaciones')
    readonly_fields = ('fecha_apertura', 'fecha_cierre')

    def estado_badge(self, obj):
        if obj.estado == CajaSesion.ESTADO_ABIERTA:
            return format_html(
                '<span class="bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400 px-2 py-1 rounded text-xs font-semibold inline-flex items-center gap-1"><i class="fa-solid fa-lock-open"></i> Abierta</span>'
            )
        return format_html(
            '<span class="bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-400 px-2 py-1 rounded text-xs font-semibold inline-flex items-center gap-1"><i class="fa-solid fa-lock"></i> Cerrada</span>'
        )
    estado_badge.short_description = "Estado"

    def exportar_cierre_link(self, obj):
        if obj.estado == CajaSesion.ESTADO_CERRADA:
            url = reverse('pos:exportar_cierre_caja', kwargs={'sesion_id': obj.id})
            return format_html(
                '<a href="{}" class="bg-cyan-100 hover:bg-cyan-200 text-cyan-800 dark:bg-cyan-950 dark:hover:bg-cyan-900 dark:text-cyan-300 px-2 py-1 rounded text-xs font-semibold inline-flex items-center gap-1"><i class="fa-solid fa-file-csv"></i> Exportar CSV</a>',
                url
            )
        return "-"
    exportar_cierre_link.short_description = "Reporte"


@admin.register(TicketPOS)
class TicketPOSAdmin(ModelAdmin):
    list_display = (
        'numero_serie',
        'pedido',
        'cajero',
        'fecha_emision',
        'total',
        'tipo_comprobante_label',
        'impreso_status',
        'imprimir_ticket_link'
    )
    list_filter = ('tipo_comprobante', 'impreso', 'fecha_emision', 'cajero')
    search_fields = ('numero_serie', 'pedido__numero_pedido', 'cajero__username', 'ruc_cliente', 'razon_social')
    readonly_fields = ('numero_serie', 'fecha_emision', 'subtotal', 'igv', 'total')

    def tipo_comprobante_label(self, obj):
        return obj.get_tipo_comprobante_display()
    tipo_comprobante_label.short_description = "Comprobante"

    def impreso_status(self, obj):
        if obj.impreso:
            return format_html(
                '<span class="bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400 px-2 py-1 rounded text-xs font-semibold inline-flex items-center gap-1"><i class="fa-solid fa-check"></i> Sí</span>'
            )
        return format_html(
            '<span class="bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400 px-2 py-1 rounded text-xs font-semibold inline-flex items-center gap-1"><i class="fa-solid fa-xmark"></i> No</span>'
        )
    impreso_status.short_description = "Impreso"

    def imprimir_ticket_link(self, obj):
        url = reverse('pos:imprimir_ticket', kwargs={'ticket_id': obj.id})
        return format_html(
            '<a href="{}" target="_blank" class="bg-amber-100 hover:bg-amber-200 text-amber-800 dark:bg-amber-950 dark:hover:bg-amber-900 dark:text-amber-300 px-2 py-1 rounded text-xs font-semibold inline-flex items-center gap-1"><i class="fa-solid fa-print"></i> Re-Imprimir</a>',
            url
        )
    imprimir_ticket_link.short_description = "Acción"


@admin.register(MovimientoCaja)
class MovimientoCajaAdmin(ModelAdmin):
    list_display = ('id', 'sesion', 'tipo', 'motivo', 'monto', 'concepto', 'registrado_por', 'fecha')
    list_filter = ('tipo', 'motivo', 'fecha')
    search_fields = ('concepto', 'sesion__id', 'registrado_por__username')
