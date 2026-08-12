from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.mantenimiento.models import EquipoRegistrado, Mantenimiento, registrar_equipos_pedido
from apps.clientes.models import Cliente
from apps.tienda.models import Producto, Categoria
from apps.pedidos.models import Pedido, DetallePedido
from apps.pagos.models import Pago

User = get_user_model()

class MantenimientoTests(TestCase):
    def setUp(self):
        # Create users
        self.tecnico = User.objects.create_user(
            username='tecnico1',
            password='Password123!',
            rol=User.ROLE_TECNICO
        )
        self.cliente_user = User.objects.create_user(
            username='cliente1',
            password='Password123!',
            rol=User.ROLE_CLIENTE
        )
        
        # Create CRM client
        self.cliente = Cliente.objects.create(
            dni_ruc='12345678',
            nombre_completo='Cliente Mantenimiento',
            tipo='persona',
            canal_origen='tienda_fisica'
        )

        # Create catalog product (tool)
        self.cat = Categoria.objects.create(nombre='Herramientas', slug='herramientas')
        self.herramienta = Producto.objects.create(
            codigo_articulo='HP2070',
            nombre='Taladro HP2070',
            slug='taladro-hp2070',
            precio_venta=Decimal('350.00'),
            stock=10,
            stock_web=10,
            tipo=Producto.TIPO_HERRAMIENTA,
            familia_sap='EQUIPOS',
            categoria=self.cat
        )
        
        # Spare parts
        self.carbones = Producto.objects.create(
            codigo_articulo='CB-85',
            nombre='Carbones CB-85',
            slug='carbones-cb-85',
            precio_venta=Decimal('15.00'),
            stock=100,
            tipo=Producto.TIPO_REPUESTO,
            familia_sap='REPUESTOS',
            categoria=self.cat
        )

        self.client = Client()

    def test_mantenimiento_access_restriction(self):
        # Unauthenticated redirects
        response = self.client.get(reverse('mantenimiento:dashboard'))
        self.assertEqual(response.status_code, 302)
        
        # Cliente restricted (403)
        self.client.login(username='cliente1', password='Password123!')
        response = self.client.get(reverse('mantenimiento:dashboard'))
        self.assertEqual(response.status_code, 403)
        self.client.logout()

    def test_auto_register_equipos_on_web_pago(self):
        # Create a paid web order
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            canal=Pedido.CANAL_WEB,
            estado=Pedido.ESTADO_PENDIENTE,
            subtotal=Decimal('350.00'),
            igv=Decimal('63.00'),
            total=Decimal('413.00')
        )
        # Note: the status is set as 'pendiente'
        DetallePedido.objects.create(
            pedido=pedido,
            producto=self.herramienta,
            cantidad=2,
            precio_unitario=Decimal('350.00')
        )
        
        # Confirmar pago vía servicio (sin Culqi; flujo Yape/tienda)
        from apps.pedidos.services import confirmar_pago_pedido
        from apps.inventario.models import MovimientoInventario
        from apps.pagos.models import Pago

        self.client.login(username='cliente1', password='Password123!')
        confirmar_pago_pedido(
            pedido=pedido,
            metodo=Pago.METODO_YAPE,
            monto=pedido.total,
            referencia_externa=f'TEST-{pedido.numero_pedido}',
            motivo_inventario=MovimientoInventario.MOTIVO_VENTA_WEB,
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Pedido.ESTADO_PAGADO)
        
        # Verify 2 equipments were auto-registered
        equipos = EquipoRegistrado.objects.filter(pedido_origin=pedido, producto=self.herramienta)
        self.assertEqual(equipos.count(), 2)
        
        # Verify serial format: WEB-ORD-{year}-XXXX-N
        for i, eq in enumerate(equipos):
            self.assertTrue(eq.numero_serie.startswith(f"WEB-{pedido.numero_pedido}"))
            self.assertEqual(eq.estado, EquipoRegistrado.ESTADO_ACTIVO)

    def test_requiere_mantenimiento_logic(self):
        # Create equipment
        equipo = EquipoRegistrado.objects.create(
            cliente=self.cliente,
            producto=self.herramienta,
            numero_serie='TEST-SN-999',
            horas_uso_actuales=120,
            horas_proximo_mantenimiento=300
        )
        self.assertFalse(equipo.requiere_mantenimiento)
        
        # Set hours to 310 (exceeds limit)
        equipo.horas_uso_actuales = 310
        equipo.save()
        self.assertTrue(equipo.requiere_mantenimiento)

    def test_mantenimiento_workflow(self):
        self.client.login(username='tecnico1', password='Password123!')
        
        # 1. Register a tool reception via nueva OT
        response = self.client.post(reverse('mantenimiento:nueva_ot'), {
            'cliente': self.cliente.id,
            'producto': self.herramienta.id,
            'numero_serie': 'WORKFLOW-SN-123',
            'origen': 'nuestro',
            'tipo': Mantenimiento.TIPO_300H,
            'diagnostico': 'Diagnóstico inicial de prueba',
            'observaciones': 'Ninguna',
            'linea_codigo': [],
            'linea_descripcion': [],
            'linea_cantidad': [],
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify equipment and order were created
        equipo = EquipoRegistrado.objects.get(numero_serie='WORKFLOW-SN-123')
        self.assertEqual(equipo.estado, EquipoRegistrado.ESTADO_MANTENIMIENTO)
        
        mantenimiento = Mantenimiento.objects.filter(equipo=equipo).first()
        self.assertIsNotNone(mantenimiento)
        self.assertTrue(mantenimiento.numero_ot.startswith('OT-'))
        self.assertEqual(mantenimiento.estado, Mantenimiento.ESTADO_INGRESADO)
        
        # 2. Edit order: process, add parts and close
        response = self.client.post(reverse('mantenimiento:editar_ot', kwargs={'mantenimiento_id': mantenimiento.id}), {
            'accion': 'guardar',
            'tipo': Mantenimiento.TIPO_300H,
            'estado': Mantenimiento.ESTADO_ENTREGADO,
            'diagnostico': 'Diagnóstico actualizado',
            'trabajos_realizados': 'Se cambiaron carbones y limpió carcasa',
            'costo_mano_obra': '45.00',
            'estado_garantia': Mantenimiento.GARANTIA_BORRADOR,
            'linea_codigo': [self.carbones.codigo_articulo],
            'linea_descripcion': [self.carbones.nombre],
            'linea_cantidad': ['1'],
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify order updates
        mantenimiento.refresh_from_db()
        self.assertEqual(mantenimiento.estado, Mantenimiento.ESTADO_ENTREGADO)
        self.assertIsNotNone(mantenimiento.fecha_entrega_real)
        
        # Verify equipment hour schedule updates
        equipo.refresh_from_db()
        self.assertEqual(equipo.estado, EquipoRegistrado.ESTADO_ACTIVO)
