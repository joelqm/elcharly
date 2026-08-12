from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.tienda.models import Producto, Categoria
from apps.clientes.models import Cliente
from .models import Pedido, DetallePedido
from apps.pagos.models import Pago

Usuario = get_user_model()

class PedidosTestCase(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Equipos Makita")
        self.producto = Producto.objects.create(
            codigo_articulo="DHP484Z",
            nombre="Taladro Atornillador 18V LXT",
            familia_sap="EQUIPOS",
            precio_venta=900.00,
            stock=10,
            stock_web=10,
            stock_minimo=2,
            categoria=self.categoria,
            mostrar_en_web=True,
        )
        self.cliente = Cliente.objects.create(
            nombre_completo="José Quispe",
            dni_ruc="45893256",
            telefono="985654123",
            correo="jose@gmail.com",
            direccion="Av. Ejército 450, Yanahuara"
        )

    def test_creacion_pedido_y_correlativo(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            canal=Pedido.CANAL_WEB,
            estado=Pedido.ESTADO_PENDIENTE,
            subtotal=762.71,
            igv=137.29,
            total=900.00,
            direccion_envio="Av. Ejército 450"
        )
        # Comprobar formato del correlativo ORD-YYYY-NNNN
        import datetime
        year = datetime.datetime.now().year
        self.assertTrue(pedido.numero_pedido.startswith(f"WEB-{year}-"))
        
        # Detalle de pedido
        detalle = DetallePedido.objects.create(
            pedido=pedido,
            producto=self.producto,
            cantidad=1,
            precio_unitario=900.00
        )
        self.assertEqual(detalle.subtotal, 900.00)

    def test_checkout_procesamiento_y_crm(self):
        # Añadir al carrito mediante el test client session
        session = self.client.session
        session['cart'] = {
            str(self.producto.id): {
                'cantidad': 2,
                'precio': '900.00'
            }
        }
        session.save()

        # Checkout actual: Yape/Plin o pagar en tienda (no tarjeta Culqi en este flujo)
        response = self.client.post('/tienda/checkout/', {
            'nombre_completo': 'José Quispe Modificado',
            'dni_ruc': '45893256',
            'telefono': '999888777',
            'correo': 'jose_new@gmail.com',
            'metodo_pago': 'yape',
            'notas': 'Llamar antes de llegar',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.endswith('/tienda/pago-manual/')
            or '/tienda/pago-manual' in response.url
        )

        self.assertEqual(Cliente.objects.count(), 1)
        cliente_crm = Cliente.objects.first()
        self.assertEqual(cliente_crm.nombre_completo, 'José Quispe Modificado')
        self.assertEqual(cliente_crm.telefono, '999888777')
        self.assertEqual(cliente_crm.correo, 'jose_new@gmail.com')

        self.assertEqual(Pedido.objects.count(), 1)
        pedido = Pedido.objects.first()
        self.assertEqual(pedido.total, 1800.00)
        self.assertEqual(pedido.estado, Pedido.ESTADO_PENDIENTE)
        self.assertEqual(pedido.detalles.count(), 1)
        self.assertEqual(pedido.detalles.first().cantidad, 2)

    def test_confirmar_pago_descuenta_stock_y_registra_equipo(self):
        from apps.pedidos.services import confirmar_pago_pedido
        from apps.mantenimiento.models import EquipoRegistrado
        from apps.inventario.models import MovimientoInventario

        pedido = Pedido.objects.create(
            cliente=self.cliente,
            canal=Pedido.CANAL_WEB,
            estado=Pedido.ESTADO_PENDIENTE,
            subtotal=762.71,
            igv=137.29,
            total=900.00,
        )
        DetallePedido.objects.create(
            pedido=pedido,
            producto=self.producto,
            cantidad=1,
            precio_unitario=900.00,
        )
        confirmar_pago_pedido(
            pedido=pedido,
            metodo=Pago.METODO_TARJETA,
            monto=900.00,
            referencia_externa='TEST-TX-1',
            motivo_inventario=MovimientoInventario.MOTIVO_VENTA_WEB,
        )
        self.producto.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(self.producto.stock, 10)  # tienda intacta
        self.assertEqual(self.producto.stock_web, 9)  # descuenta web
        self.assertEqual(pedido.estado, Pedido.ESTADO_PAGADO)
        self.assertEqual(EquipoRegistrado.objects.filter(pedido_origin=pedido).count(), 1)
