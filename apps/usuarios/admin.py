from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from .models import Usuario

@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin, ModelAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Información de Rol y Contacto', {'fields': ('rol', 'telefono', 'dni_ruc')}),
        ('Sedes', {'fields': ('sedes', 'sede_activa')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Información de Rol y Contacto', {'fields': ('rol', 'telefono', 'dni_ruc')}),
        ('Sedes', {'fields': ('sedes', 'sede_activa')}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'rol', 'sede_activa', 'is_staff')
    list_filter = ('rol', 'is_staff', 'is_superuser', 'is_active', 'sedes')
    filter_horizontal = ('sedes', 'groups', 'user_permissions')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'dni_ruc')
    ordering = ('username',)
