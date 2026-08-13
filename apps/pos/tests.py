from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.pos.models import CajaSesion, TicketPOS
from apps.pedidos.models import Pedido
from apps.clientes.models import Cliente
from apps.tienda.models import Producto, Categoria
from apps.pagos.models import Pago
from apps.sistema.models import Empresa, Sede

User = get_user_model()

class POSTests(TestCase):
    def setUp(self):
        # Create user with vendedor role
        self.cajero = User.objects.create_user(
            username='cajero1',
            password='Password123!',
            rol=User.ROLE_VENDEDOR
        )
        # Create user with customer role (to check restriction)
        self.cliente_user = User.objects.create_user(
            username='cliente1',
            password='Password123!',
            rol=User.ROLE_CLIENTE
        )

        empresa = Empresa.objects.create(nombre='El Charly', nombre_corto='El Charly', ruc='10431549001')
        self.sede = Sede.objects.create(
            empresa=empresa, codigo='tienda', nombre='Tienda',
            tipo=Sede.TIPO_TIENDA, compartir_productos=True,
        )
        self.cajero.sedes.add(self.sede)
        self.cajero.sede_activa = self.sede
        self.cajero.save()

        # Create category and products
        self.cat = Categoria.objects.create(nombre='Herramientas', slug='herramientas')
        self.prod1 = Producto.objects.create(
            codigo_articulo='HP2070',
            nombre='Taladro HP2070',
            slug='taladro-hp2070',
            precio_venta=Decimal('350.00'),
            stock=10,
            categoria=self.cat
        )
        self.prod2 = Producto.objects.create(
            codigo_articulo='DHP484Z',
            nombre='Rotomartillo DHP484Z',
            slug='rotomartillo-dhp484z',
            precio_venta=Decimal('620.00'),
            stock=3,
            categoria=self.cat
        )

        self.client = Client()

    def test_pos_access_restriction(self):
        # Visitante → login del POS
        response = self.client.get(reverse('pos:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/pos/login/', response.url)

        # Cliente logueado: 404 (sin acceso al sistema interno)
        self.client.login(username='cliente1', password='Password123!')
        response = self.client.get(reverse('pos:dashboard'))
        self.assertEqual(response.status_code, 404)
        self.client.logout()

    def test_caja_session_flow(self):
        self.client.login(username='cajero1', password='Password123!')
        
        # Accessing dashboard redirects to opening caja page if no open session exists
        response = self.client.get(reverse('pos:dashboard'))
        self.assertRedirects(response, reverse('pos:abrir_caja'))
        
        # Open session POST
        response = self.client.post(reverse('pos:abrir_caja'), {
            'monto_apertura': '150.00',
            'observaciones': 'Caja de prueba',
            'sede_id': str(self.sede.id),
        })
        self.assertRedirects(response, reverse('pos:dashboard'))
        
        # Verify session was created
        sesion = CajaSesion.objects.filter(cajero=self.cajero, estado=CajaSesion.ESTADO_ABIERTA).first()
        self.assertIsNotNone(sesion)
        self.assertEqual(sesion.monto_apertura, Decimal('150.00'))
        
        # Accessing dashboard should now be successful
        response = self.client.get(reverse('pos:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Caja abierta")
        
        # Close session POST
        response = self.client.post(reverse('pos:cerrar_caja', kwargs={'sesion_id': sesion.id}), {
            'monto_cierre': '150.00',
            'observaciones': 'Arqueo realizado'
        })
        self.assertRedirects(response, reverse('pos:cerrar_caja', kwargs={'sesion_id': sesion.id}))
        
        # Check closed session status
        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, CajaSesion.ESTADO_CERRADA)
        self.assertEqual(sesion.monto_cierre, Decimal('150.00'))

    def test_registrar_venta_pos(self):
        self.client.login(username='cajero1', password='Password123!')
        
        # Open session first
        sesion = CajaSesion.objects.create(
            cajero=self.cajero,
            sede=self.sede,
            monto_apertura=Decimal('100.00'),
            estado=CajaSesion.ESTADO_ABIERTA
        )

        # Register sale POST (JSON) — solo ticket interno
        payload = {
            'cliente_dni_ruc': '77777777',
            'cliente_nombre': 'Test Customer CRM',
            'cliente_telefono': '999888777',
            'cliente_correo': 'test@gmail.com',
            'cliente_direccion': 'Calle Lima 123',
            'metodo_pago': 'efectivo',
            'tipo_comprobante': 'ticket',
            'descuento': '20.00',
            'items': [
                {'id': self.prod1.id, 'cantidad': 2, 'precio': 350.00},
                {'id': self.prod2.id, 'cantidad': 1, 'precio': 600.00}
            ]
        }

        response = self.client.post(
            reverse('pos:registrar_venta'),
            data=payload,
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data['success'])
        self.assertIn('ticket_id', res_data)

        ticket = TicketPOS.objects.get(id=res_data['ticket_id'])
        self.assertEqual(ticket.total, Decimal('1280.00'))

        self.prod1.refresh_from_db()
        self.prod2.refresh_from_db()
        self.assertEqual(self.prod1.stock, 8)
        self.assertEqual(self.prod2.stock, 2)

        cliente = Cliente.objects.filter(dni_ruc='77777777').first()
        self.assertIsNotNone(cliente)
        self.assertEqual(cliente.nombre_completo, 'Test Customer CRM')

        self.assertTrue(ticket.numero_serie.startswith('T-'))
        pedido = Pedido.objects.get(id=ticket.pedido_id)
        self.assertEqual(pedido.canal, Pedido.CANAL_POS)
        self.assertEqual(pedido.estado, Pedido.ESTADO_ENTREGADO)
        self.assertFalse(pedido.es_historica)
        self.assertEqual(pedido.caja_sesion_id, sesion.id)

    def test_registrar_venta_historica_no_toca_stock_ni_caja(self):
        self.client.login(username='cajero1', password='Password123!')
        sesion = CajaSesion.objects.create(
            cajero=self.cajero,
            sede=self.sede,
            monto_apertura=Decimal('100.00'),
            estado=CajaSesion.ESTADO_ABIERTA,
        )
        ayer = timezone.localdate() - timedelta(days=1)
        stock_antes = self.prod2.stock
        payload = {
            'cliente_varios': True,
            'metodo_pago': 'efectivo',
            'tipo_comprobante': 'ticket',
            'fecha_venta': ayer.isoformat(),
            'items': [
                {'id': self.prod2.id, 'cantidad': 5, 'precio': 620.00},
            ],
        }
        response = self.client.post(
            reverse('pos:registrar_venta'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['success'])

        self.prod2.refresh_from_db()
        self.assertEqual(self.prod2.stock, stock_antes)

        ticket = TicketPOS.objects.get(id=response.json()['ticket_id'])
        pedido = ticket.pedido
        self.assertTrue(pedido.es_historica)
        self.assertIsNone(pedido.caja_sesion_id)
        self.assertEqual(timezone.localdate(pedido.fecha_pedido), ayer)
        self.assertEqual(timezone.localdate(ticket.fecha_emision), ayer)
        pago = Pago.objects.filter(pedido=pedido).first()
        self.assertIsNotNone(pago)
        self.assertEqual(timezone.localdate(pago.fecha_pago), ayer)

    def test_registrar_venta_fecha_futura_rechazada(self):
        self.client.login(username='cajero1', password='Password123!')
        CajaSesion.objects.create(
            cajero=self.cajero,
            sede=self.sede,
            monto_apertura=Decimal('100.00'),
            estado=CajaSesion.ESTADO_ABIERTA,
        )
        manana = timezone.localdate() + timedelta(days=1)
        payload = {
            'cliente_varios': True,
            'metodo_pago': 'efectivo',
            'tipo_comprobante': 'ticket',
            'fecha_venta': manana.isoformat(),
            'items': [
                {'id': self.prod1.id, 'cantidad': 1, 'precio': 350.00},
            ],
        }
        response = self.client.post(
            reverse('pos:registrar_venta'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('futura', response.json()['error'])
        self.assertFalse(Pedido.objects.exists())

    def test_anular_venta_pos_devuelve_stock_y_sale_de_caja(self):
        self.client.login(username='cajero1', password='Password123!')
        sesion = CajaSesion.objects.create(
            cajero=self.cajero,
            sede=self.sede,
            monto_apertura=Decimal('100.00'),
            estado=CajaSesion.ESTADO_ABIERTA,
        )
        payload = {
            'cliente_varios': True,
            'metodo_pago': 'efectivo',
            'tipo_comprobante': 'ticket',
            'items': [
                {'id': self.prod1.id, 'cantidad': 1, 'precio': 350.00},
            ],
        }
        response = self.client.post(
            reverse('pos:registrar_venta'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        ticket = TicketPOS.objects.get(id=response.json()['ticket_id'])
        pedido = ticket.pedido
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.stock, 9)

        anular = self.client.post(
            reverse('pos:hub_pedido_detalle', args=[pedido.id]),
            {'accion': 'anular_venta'},
        )
        self.assertEqual(anular.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Pedido.ESTADO_CANCELADO)
        self.assertFalse(pedido.puede_anular)
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.stock, 10)
        pago = Pago.objects.get(pedido=pedido)
        self.assertEqual(pago.estado, Pago.ESTADO_REEMBOLSADO)

    def test_registrar_venta_usa_stock_web_automatico(self):
        """Si tienda=0 y web>0, la venta POS descuenta web sin transferencia manual."""
        self.client.login(username='cajero1', password='Password123!')
        CajaSesion.objects.create(
            cajero=self.cajero,
            sede=self.sede,
            monto_apertura=Decimal('100.00'),
            estado=CajaSesion.ESTADO_ABIERTA,
        )
        self.prod2.stock = 0
        self.prod2.stock_web = 2
        self.prod2.save(update_fields=['stock', 'stock_web'])

        payload = {
            'cliente_varios': True,
            'metodo_pago': 'efectivo',
            'tipo_comprobante': 'ticket',
            'items': [
                {'id': self.prod2.id, 'cantidad': 1, 'precio': 620.00},
            ],
        }
        response = self.client.post(
            reverse('pos:registrar_venta'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['success'])
        self.prod2.refresh_from_db()
        self.assertEqual(self.prod2.stock, 0)
        self.assertEqual(self.prod2.stock_web, 1)

    def test_registrar_venta_insufficient_stock(self):
        self.client.login(username='cajero1', password='Password123!')
        
        # Open session first
        CajaSesion.objects.create(
            cajero=self.cajero,
            sede=self.sede,
            monto_apertura=Decimal('100.00'),
            estado=CajaSesion.ESTADO_ABIERTA
        )

        payload = {
            'cliente_varios': True,
            'cliente_dni_ruc': '00000000',
            'cliente_nombre': 'Cliente Varios',
            'metodo_pago': 'tarjeta',
            'tipo_comprobante': 'ticket',
            'items': [
                {'id': self.prod2.id, 'cantidad': 5, 'precio': 620.00}
            ]
        }
        
        response = self.client.post(
            reverse('pos:registrar_venta'),
            data=payload,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Stock insuficiente', response.json()['error'])

    def test_hub_inventario_ingreso_rapido(self):
        self.client.login(username='cajero1', password='Password123!')
        self.prod1.stock = 0
        self.prod1.save(update_fields=['stock'])

        payload = {
            'producto_id': self.prod1.id,
            'cantidad': 5,
            'motivo': 'Ingreso prueba rápida POS'
        }
        response = self.client.post(
            reverse('pos:hub_inventario_ingreso_rapido'),
            data=payload,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['stock_tienda'], 5)

        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.stock, 5)

