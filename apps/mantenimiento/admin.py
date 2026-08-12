from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import EquipoRegistrado, Mantenimiento, OrdenTrabajoLinea, ContadorOT


class OrdenTrabajoLineaInline(TabularInline):
    model = OrdenTrabajoLinea
    extra = 1


@admin.register(ContadorOT)
class ContadorOTAdmin(ModelAdmin):
    list_display = ('id', 'ultimo', 'proximo_display')
    fields = ('ultimo',)

    @admin.display(description='Próxima OT')
    def proximo_display(self, obj):
        return f'OT-{obj.ultimo + 1}'


@admin.register(EquipoRegistrado)
class EquipoRegistradoAdmin(ModelAdmin):
    list_display = (
        'numero_serie',
        'cliente',
        'producto_label',
        'origen',
        'horas_uso_actuales',
        'requiere_mantenimiento_badge',
        'estado_badge',
    )
    list_filter = ('estado', 'origen', 'producto', 'fecha_registro')
    search_fields = (
        'numero_serie', 'cliente__nombre_completo', 'cliente__dni_ruc',
        'modelo_alternativo', 'boleta_factura',
    )
    readonly_fields = ('fecha_registro',)

    def producto_label(self, obj):
        if obj.producto:
            return obj.producto.nombre
        return obj.modelo_alternativo
    producto_label.short_description = 'Equipo / Modelo'

    def requiere_mantenimiento_badge(self, obj):
        if obj.requiere_mantenimiento:
            return format_html(
                '<span class="bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-semibold">Sí (Alerta)</span>'
            )
        return format_html(
            '<span class="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-xs font-semibold">Al día</span>'
        )
    requiere_mantenimiento_badge.short_description = 'Requiere Mant.'

    def estado_badge(self, obj):
        if obj.estado == EquipoRegistrado.ESTADO_ACTIVO:
            return format_html('<span class="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-xs font-semibold">Activo</span>')
        elif obj.estado == EquipoRegistrado.ESTADO_MANTENIMIENTO:
            return format_html('<span class="bg-amber-100 text-amber-700 px-2 py-1 rounded text-xs font-semibold">En Taller</span>')
        return format_html('<span class="bg-slate-100 text-slate-700 px-2 py-1 rounded text-xs font-semibold">Baja</span>')
    estado_badge.short_description = 'Estado'


@admin.register(Mantenimiento)
class MantenimientoAdmin(ModelAdmin):
    list_display = (
        'numero_ot',
        'equipo',
        'tipo_label',
        'tecnico',
        'estado_badge',
        'estado_garantia',
        'total',
        'fecha_ingreso',
    )
    list_filter = ('estado', 'tipo', 'estado_garantia', 'tecnico', 'fecha_ingreso')
    search_fields = (
        'numero_ot', 'id', 'equipo__numero_serie',
        'equipo__cliente__nombre_completo', 'diagnostico', 'autorizacion_mpe',
    )
    readonly_fields = ('fecha_ingreso', 'fecha_entrega_real', 'total', 'numero_ot')
    filter_horizontal = ('repuestos_usados',)
    inlines = [OrdenTrabajoLineaInline]

    def tipo_label(self, obj):
        return obj.get_tipo_display()
    tipo_label.short_description = 'Tipo'

    def estado_badge(self, obj):
        if obj.estado == Mantenimiento.ESTADO_INGRESADO:
            return format_html(
                '<span class="bg-cyan-100 text-cyan-700 px-2 py-1 rounded text-xs font-semibold">Ingresado</span>'
            )
        elif obj.estado == Mantenimiento.ESTADO_PROCESO:
            return format_html(
                '<span class="bg-amber-100 text-amber-700 px-2 py-1 rounded text-xs font-semibold">En Proceso</span>'
            )
        elif obj.estado == Mantenimiento.ESTADO_LISTO:
            return format_html(
                '<span class="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-xs font-semibold">Listo</span>'
            )
        return format_html(
            '<span class="bg-slate-100 text-slate-700 px-2 py-1 rounded text-xs font-semibold">Entregado</span>'
        )
    estado_badge.short_description = 'Estado'
