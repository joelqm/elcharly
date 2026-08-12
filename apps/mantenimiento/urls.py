from django.urls import path
from . import views

app_name = 'mantenimiento'

urlpatterns = [
    path('mantenimiento/', views.tecnico_dashboard, name='dashboard'),
    path('mantenimiento/buscar/', views.buscar_historial, name='buscar'),
    path('mantenimiento/ot/nueva/', views.nueva_ot, name='nueva_ot'),
    path('mantenimiento/ot/<int:mantenimiento_id>/', views.editar_ot, name='editar_ot'),
    path('mantenimiento/ingresar/', views.registrar_ingreso, name='registrar_ingreso'),
    path('mantenimiento/<int:mantenimiento_id>/editar/', views.editar_mantenimiento, name='editar_mantenimiento'),
    path('mantenimiento/equipo/<int:equipo_id>/', views.historial_equipo, name='historial_equipo'),
]
