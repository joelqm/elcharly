from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
import datetime

from apps.clientes.models import Cliente
from apps.tienda.models import Producto, Categoria
from apps.pedidos.models import Pedido, DetallePedido
from apps.mantenimiento.models import EquipoRegistrado
from apps.cotizaciones.models import Cotizacion

User = get_user_model()

class ReportesTests(TestCase):
    def setUp(self):
        # Create users
        self.admin = User.objects.create_user(
            username='admin1',
            password='Password123!',
            rol=User.ROLE_ADMIN
        )
        self.vendedor = User.objects.create_user(
            username='vendedor1',
            password='Password123!',
            rol=User.ROLE_VENDEDOR
        )
        self.cliente_user = User.objects.create_user(
            username='cliente1',
            password='Password123!',
            rol=User.ROLE_CLIENTE
        )

        # Create Client
        self.cliente = Cliente.objects.create(
            nombre_completo='Raul Prado',
            tipo=Cliente.TIPO_PERSONA,
            dni_ruc='11223344'
        )

        # Create Catalog Product
        self.cat = Categoria.objects.create(nombre='Herramientas', slug='herramientas')
        self.herramienta = Producto.objects.create(
            codigo_articulo='DDF484',
            nombre='Taladro DDF484',
            slug='taladro-ddf484',
            precio_venta=Decimal('500.00'),
            stock=10,
            tipo=Producto.TIPO_HERRAMIENTA,
            categoria=self.cat
        )

        self.client = Client()

    def test_reportes_access_restriction(self):
        # Anonymous redirects
        response = self.client.get(reverse('reportes:dashboard'))
        self.assertEqual(response.status_code, 302)
        
        # Cliente restricted (403)
        self.client.login(username='cliente1', password='Password123!')
        response = self.client.get(reverse('reportes:dashboard'))
        self.assertEqual(response.status_code, 403)
        self.client.logout()
        
        # Vendedor allowed (200)
        self.client.login(username='vendedor1', password='Password123!')
        response = self.client.get(reverse('reportes:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.client.logout()

    def test_dashboard_calculations_and_data(self):
        # 1. Create a paid order for today
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            canal=Pedido.CANAL_POS,
            estado=Pedido.ESTADO_PAGADO,
            subtotal=Decimal('500.00'),
            igv=Decimal('90.00'),
            total=Decimal('590.00')
        )
        DetallePedido.objects.create(
            pedido=pedido,
            producto=self.herramienta,
            cantidad=1,
            precio_unitario=Decimal('500.00'),
            subtotal=Decimal('500.00')
        )

        # 2. Create an equipment needing maintenance (Hours exceed limit)
        EquipoRegistrado.objects.create(
            cliente=self.cliente,
            producto=self.herramienta,
            numero_serie='ALERTA-SN-888',
            horas_uso_actuales=350,
            horas_proximo_mantenimiento=300,
            estado=EquipoRegistrado.ESTADO_ACTIVO
        )

        # 3. Create a pending quote
        Cotizacion.objects.create(
            cliente=self.cliente,
            modelo_equipo='DDF484',
            estado=Cotizacion.ESTADO_ENVIADA,
            total=Decimal('150.00')
        )

        # Fetch dashboard as admin
        self.client.login(username='admin1', password='Password123!')
        response = self.client.get(reverse('reportes:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Verify calculated context variables
        self.assertEqual(response.context['ventas_hoy'], Decimal('590.00'))
        self.assertEqual(response.context['ventas_mes'], Decimal('590.00'))
        self.assertEqual(response.context['count_hoy'], 1)
        
        # Top products
        top_prods = list(response.context['productos_mas_vendidos'])
        self.assertEqual(len(top_prods), 1)
        self.assertEqual(top_prods[0]['producto__codigo_articulo'], 'DDF484')
        self.assertEqual(top_prods[0]['cantidad_vendida'], 1)
        
        # Maintenance alerts count
        self.assertEqual(response.context['equipos_alerta'].count(), 1)
        self.assertEqual(response.context['equipos_alerta'].first().numero_serie, 'ALERTA-SN-888')

        # Pending quotes
        self.assertEqual(len(response.context['cotizaciones_pendientes']), 1)
        self.assertEqual(response.context['cotizaciones_pendientes'].first().modelo_equipo, 'DDF484')

    def test_exportar_reportes_excel_download(self):
        self.client.login(username='admin1', password='Password123!')
        response = self.client.get(reverse('reportes:excel'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertTrue(response['Content-Disposition'].startswith('attachment; filename="reporte_general_'))
