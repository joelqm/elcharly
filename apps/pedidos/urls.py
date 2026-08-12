from django.urls import path
from .views import (
    checkout,
    pago_exitoso,
    pago_manual_instrucciones,
    subir_voucher,
    lista_pedidos_staff,
    cambiar_estado_pedido,
    seguimiento_pedido,
)

app_name = 'pedidos'

urlpatterns = [
    path('tienda/checkout/', checkout, name='checkout'),
    path('tienda/pago-exitoso/', pago_exitoso, name='pago_exitoso'),
    path('tienda/pago-manual/', pago_manual_instrucciones, name='pago_manual_instrucciones'),
    path('tienda/pago-manual/voucher/', subir_voucher, name='subir_voucher'),
    path('mi-pedido/', seguimiento_pedido, name='seguimiento'),
    path('pedidos/staff/', lista_pedidos_staff, name='lista_staff'),
    path('pedidos/staff/<int:pedido_id>/estado/', cambiar_estado_pedido, name='cambiar_estado'),
]
