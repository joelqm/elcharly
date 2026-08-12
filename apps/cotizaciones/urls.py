from django.urls import path
from . import views

app_name = 'cotizaciones'

urlpatterns = [
    path('cotizaciones/', views.cotizacion_lista, name='lista'),
    path('cotizaciones/nueva/', views.cotizacion_nueva, name='nueva'),
    path('cotizaciones/buscar-clientes/', views.buscar_clientes, name='buscar_clientes'),
    path('cotizaciones/<int:cotizacion_id>/', views.cotizacion_detalle, name='detalle'),
    path('cotizaciones/<int:cotizacion_id>/editar/', views.cotizacion_editar, name='editar'),
    path('cotizaciones/<int:cotizacion_id>/anular/', views.anular_cotizacion, name='anular'),
    path('cotizaciones/<int:cotizacion_id>/pdf/', views.generar_pdf, name='pdf'),
    path('cotizaciones/<int:cotizacion_id>/excel/', views.generar_excel, name='excel'),
    path('cotizaciones/<int:cotizacion_id>/aprobar/', views.aprobar_cotizacion, name='aprobar'),
    # Rutas públicas (sin inicio de sesión POS)
    path('cotizacion/publica/<uuid:token>/', views.cotizacion_publica_ver, name='publica_ver'),
    path('cotizacion/publica/<uuid:token>/pdf/', views.cotizacion_publica_pdf, name='publica_pdf'),
]
