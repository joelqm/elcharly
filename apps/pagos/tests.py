from django.test import TestCase
from apps.tienda.models import Producto, Categoria
from apps.clientes.models import Cliente
from apps.pedidos.models import Pedido
from .models import Pago

class PagosTestCase(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Herramientas")
        self.producto = Producto.objects.create(
            codigo_articulo="DHP484Z",
            nombre="Taladro",
            familia_sap="EQUIPOS",
            precio_venta=900.00,
            stock=10,
            stock_minimo=2,
            categoria=self.categoria
        )
        self.cliente = Cliente.objects.create(
            nombre_completo="José Quispe",
            dni_ruc="45893256"
        )
        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            canal=Pedido.CANAL_WEB,
            estado=Pedido.ESTADO_PENDIENTE,
            subtotal=762.71,
            igv=137.29,
            total=900.00
        )

    def test_pago_aprobado_actualiza_pedido(self):
        pago = Pago.objects.create(
            pedido=self.pedido,
            metodo=Pago.METODO_TARJETA,
            monto=900.00,
            estado=Pago.ESTADO_APROBADO,
            referencia_externa="TX-123"
        )
        # El pedido debe haber cambiado a pagado
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, Pedido.ESTADO_PAGADO)
        self.assertEqual(pago.estado, Pago.ESTADO_APROBADO)
