from django.urls import path
from . import views

app_name = 'reportes'

urlpatterns = [
    path('reportes/', views.dashboard_reportes, name='dashboard'),
    path('reportes/excel/', views.exportar_reportes_excel, name='excel'),
]
