from django.urls import path
from .views import (
    CustomLoginView,
    custom_logout_view,
    dashboard_placeholder,
    registro_cliente,
    mi_cuenta,
)

app_name = 'usuarios'

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', custom_logout_view, name='logout'),
    path('registro/', registro_cliente, name='registro'),
    path('mi-cuenta/', mi_cuenta, name='mi_cuenta'),
    path('dashboard/<str:dashboard>/', dashboard_placeholder, name='dashboard_placeholder'),
]
