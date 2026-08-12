from django.urls import path
from . import views

app_name = 'clientes'

urlpatterns = [
    path('clientes/', views.cliente_lista, name='lista'),
    path('clientes/crear/', views.cliente_crear, name='crear'),
    path('clientes/<int:cliente_id>/', views.cliente_detalle, name='detalle'),
]
