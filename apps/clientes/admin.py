from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Cliente

@admin.register(Cliente)
class ClienteAdmin(ModelAdmin):
    list_display = ('nombre_completo', 'tipo', 'dni_ruc', 'telefono', 'correo', 'etiqueta', 'fecha_registro')
    list_filter = ('tipo', 'etiqueta', 'canal_origen', 'ciudad', 'fecha_registro')
    search_fields = ('nombre_completo', 'dni_ruc', 'telefono', 'correo')
    ordering = ('nombre_completo',)
    
