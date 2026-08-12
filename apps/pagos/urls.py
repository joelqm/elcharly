from django.urls import path
from . import views

app_name = 'pagos'

urlpatterns = [
    path('pagos/pendientes/', views.lista_pagos_pendientes, name='lista_pendientes'),
    path('pagos/<int:pago_id>/aprobar/', views.aprobar_pago, name='aprobar'),
    path('pagos/<int:pago_id>/rechazar/', views.rechazar_pago, name='rechazar'),
]
