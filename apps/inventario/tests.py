from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.tienda.models import Producto
from .models import MovimientoInventario

Usuario = get_user_model()

class InventarioTestCase(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(
            username='admin_inv',
            password='password123',
            rol='admin'
        )
        self.producto = Producto.objects.create(
            codigo_articulo="103154900",
            nombre="WIDE REFLECTOR NOZZLE 75MM",
            familia_sap="ACCESORIOS",
            precio_venta=34.17,
            stock=10,
            stock_minimo=3
        )

    def test_stock_aumenta_con_entrada(self):
        # Creamos una entrada de 5 unidades
        movimiento = MovimientoInventario.objects.create(
            producto=self.producto,
            tipo=MovimientoInventario.TIPO_ENTRADA,
            cantidad=5,
            motivo=MovimientoInventario.MOTIVO_COMPRA,
            usuario=self.user
        )
        # Recargamos el producto de la base de datos
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 15)
        self.assertEqual(movimiento.usuario, self.user)

    def test_stock_disminuye_con_salida(self):
        # Creamos una salida de 4 unidades (ej. venta POS)
        movimiento = MovimientoInventario.objects.create(
            producto=self.producto,
            tipo=MovimientoInventario.TIPO_SALIDA,
            cantidad=4,
            motivo=MovimientoInventario.MOTIVO_VENTA_POS,
            usuario=self.user
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 6)

    def test_transferencia_tienda_a_web(self):
        self.producto.stock_web = 0
        self.producto.save(update_fields=['stock_web'])
        MovimientoInventario.objects.create(
            producto=self.producto,
            tipo=MovimientoInventario.TIPO_SALIDA,
            cantidad=2,
            motivo=MovimientoInventario.MOTIVO_TRANSFERENCIA,
            destino=MovimientoInventario.DESTINO_TIENDA,
            usuario=self.user,
        )
        self.producto.refresh_from_db()
        MovimientoInventario.objects.create(
            producto=self.producto,
            tipo=MovimientoInventario.TIPO_ENTRADA,
            cantidad=2,
            motivo=MovimientoInventario.MOTIVO_TRANSFERENCIA,
            destino=MovimientoInventario.DESTINO_WEB,
            usuario=self.user,
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 8)
        self.assertEqual(self.producto.stock_web, 2)
