from django.urls import path
from django.shortcuts import redirect
from .views import (
    home,
    catalogo_productos,
    detalle_producto,
    cart_add,
    cart_remove,
    cart_detail,
)

app_name = 'tienda'

urlpatterns = [
    path('', home, name='home'),
    path('catalogo/', catalogo_productos, name='catalogo'),
    path('catalogo/producto/<slug:slug>/', detalle_producto, name='detalle'),
    path('tienda/carrito/', cart_detail, name='cart_detail'),
    path('tienda/carrito/add/<int:producto_id>/', cart_add, name='cart_add'),
    path('tienda/carrito/remove/<int:producto_id>/', cart_remove, name='cart_remove'),
    # Compatibilidad con URLs antiguas
    path('tienda/', lambda r: redirect('tienda:catalogo', permanent=False)),
    path('tienda/producto/<slug:slug>/', lambda r, slug: redirect('tienda:detalle', slug=slug)),
]
