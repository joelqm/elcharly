from django.conf import settings
from apps.tienda.cart import Cart


def cart(request):
    try:
        c = Cart(request)
        return {'cart': c, 'cart_item_count': len(c)}
    except Exception:
        return {'cart': None, 'cart_item_count': 0}


def negocio(request):
    return {'negocio': getattr(settings, 'NEGOCIO', {})}
