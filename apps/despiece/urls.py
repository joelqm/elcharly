from django.urls import path
from . import views

app_name = 'despiece'

urlpatterns = [
    path('pos/despieces/', views.despiece_lista, name='despiece_lista'),
    path('pos/despieces/subir/', views.despiece_subir, name='despiece_subir'),
    path('pos/despieces/escanear/', views.despiece_escanear_directorio, name='despiece_escanear'),
    path('pos/despieces/<str:modelo>/hotspot/', views.despiece_guardar_hotspot, name='despiece_guardar_hotspot'),
    path('pos/despieces/<str:modelo>/', views.despiece_visor, name='despiece_visor'),
]
