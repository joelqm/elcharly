from decimal import Decimal
from django.conf import settings
from apps.tienda.models import Producto


class CartStockError(Exception):
    def __init__(self, mensaje):
        self.mensaje = mensaje
        super().__init__(mensaje)


class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(settings.CART_SESSION_ID)
        if not cart:
            cart = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart

    def add(self, producto, cantidad=1, override_cantidad=False):
        producto_id = str(producto.id)
        if producto.stock_web <= 0:
            raise CartStockError(
                f"«{producto.nombre}» no tiene stock disponible en la web."
            )

        actual = 0
        if producto_id in self.cart:
            actual = self.cart[producto_id]['cantidad']

        if override_cantidad:
            nueva = max(0, cantidad)
        else:
            nueva = actual + cantidad

        if nueva <= 0:
            self.remove(producto)
            return

        if nueva > producto.stock_web:
            raise CartStockError(
                f"Stock insuficiente para «{producto.nombre}». "
                f"Disponible en web: {producto.stock_web} unidad(es)."
            )

        precio = str(producto.precio_publico)
        if producto_id not in self.cart:
            self.cart[producto_id] = {
                'cantidad': 0,
                'precio': precio,
            }

        self.cart[producto_id]['cantidad'] = nueva
        self.cart[producto_id]['precio'] = precio
        self.save()

    def save(self):
        self.session.modified = True

    def remove(self, producto):
        producto_id = str(producto.id)
        if producto_id in self.cart:
            del self.cart[producto_id]
            self.save()

    def __iter__(self):
        producto_ids = self.cart.keys()
        productos = {str(p.id): p for p in Producto.objects.filter(id__in=producto_ids)}

        for producto_id, item in self.cart.items():
            if producto_id in productos:
                yield {
                    'producto': productos[producto_id],
                    'precio': Decimal(item['precio']),
                    'cantidad': item['cantidad'],
                    'subtotal': Decimal(item['precio']) * item['cantidad'],
                }

    def __len__(self):
        return sum(item['cantidad'] for item in self.cart.values())

    def get_subtotal(self):
        return sum(
            Decimal(item['precio']) * item['cantidad']
            for item in self.cart.values()
        )

    def get_igv(self):
        total = self.get_total()
        base = total / Decimal('1.18')
        return total - base

    def get_total(self):
        return self.get_subtotal()

    def clear(self):
        del self.session[settings.CART_SESSION_ID]
        self.save()
