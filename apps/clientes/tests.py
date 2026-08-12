from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import Cliente
from apps.pedidos.models import Pedido

User = get_user_model()

class ClientesCRMTests(TestCase):
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
        
        # Create a client
        self.cliente = Cliente.objects.create(
            nombre_completo='Corporación Makita Sac',
            tipo=Cliente.TIPO_EMPRESA,
            dni_ruc='20123456789',
            telefono='987654321',
            correo='contacto@makitasac.pe',
            etiqueta=Cliente.ETIQUETA_NUEVO
        )
        
        self.client = Client()

    def test_crm_access_restriction(self):
        # Visitante → login del POS
        response = self.client.get(reverse('clientes:lista'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/pos/login/', response.url)

        # Cliente logueado: 404
        self.client.login(username='cliente1', password='Password123!')
        response = self.client.get(reverse('clientes:lista'))
        self.assertEqual(response.status_code, 404)
        self.client.logout()

        # Vendedor and Admin roles get access (200)
        self.client.login(username='vendedor1', password='Password123!')
        response = self.client.get(reverse('clientes:lista'))
        self.assertEqual(response.status_code, 200)
        self.client.logout()

    def test_cliente_model_properties_and_sugerencia(self):
        # By default, since no paid orders exist, stats are 0
        self.assertEqual(self.cliente.numero_pedidos, 0)
        self.assertEqual(self.cliente.total_comprado, 0)
        self.assertEqual(self.cliente.etiqueta_sugerida, 'Empresa') # Corporate is Empresa
        
        # Create a personal client
        persona = Cliente.objects.create(
            nombre_completo='Juan Pérez',
            tipo=Cliente.TIPO_PERSONA,
            dni_ruc='45678912',
            etiqueta=Cliente.ETIQUETA_NUEVO
        )
        self.assertEqual(persona.etiqueta_sugerida, 'Cliente Nuevo')
        
        # Create 3 paid orders for persona
        for i in range(3):
            Pedido.objects.create(
                cliente=persona,
                canal=Pedido.CANAL_POS,
                estado=Pedido.ESTADO_PAGADO,
                subtotal=Decimal('100.00'),
                igv=Decimal('18.00'),
                total=Decimal('118.00')
            )
            
        persona.refresh_from_db()
        self.assertEqual(persona.numero_pedidos, 3)
        self.assertEqual(persona.total_comprado, Decimal('354.00'))
        self.assertEqual(persona.etiqueta_sugerida, 'Cliente Frecuente')
        
        # Increase spent amount to VIP
        Pedido.objects.create(
            cliente=persona,
            canal=Pedido.CANAL_POS,
            estado=Pedido.ESTADO_PAGADO,
            subtotal=Decimal('4237.29'),
            igv=Decimal('762.71'),
            total=Decimal('5000.00')
        )
        self.assertEqual(persona.etiqueta_sugerida, 'VIP')

    def test_cliente_update_view(self):
        self.client.login(username='vendedor1', password='Password123!')
        
        # Edit Juan
        response = self.client.post(reverse('clientes:detalle', kwargs={'cliente_id': self.cliente.id}), {
            'nombre_completo': 'Corporación Makita S.A.C. Actualizado',
            'dni_ruc': '20123456789',
            'telefono': '955443322',
            'correo': 'contacto_nuevo@makitasac.pe',
            'direccion': 'Av. Parra 456',
            'ciudad': 'Arequipa',
            'etiqueta': Cliente.ETIQUETA_VIP,
            'notas': 'Cliente VIP estratégico'
        })
        self.assertRedirects(response, reverse('clientes:detalle', kwargs={'cliente_id': self.cliente.id}))
        
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre_completo, 'Corporación Makita S.A.C. Actualizado')
        self.assertEqual(self.cliente.telefono, '955443322')
        self.assertEqual(self.cliente.etiqueta, Cliente.ETIQUETA_VIP)
        self.assertEqual(self.cliente.notas, 'Cliente VIP estratégico')

    def test_cliente_crear_view(self):
        self.client.login(username='admin1', password='Password123!')
        
        response = self.client.post(reverse('clientes:crear'), {
            'nombre_completo': 'María Flores',
            'tipo': Cliente.TIPO_PERSONA,
            'dni_ruc': '98765432',
            'telefono': '912345678',
            'correo': 'maria@gmail.com',
            'direccion': 'Cerro Colorado',
            'ciudad': 'Arequipa',
            'etiqueta': Cliente.ETIQUETA_NUEVO,
            'notas': 'Interesada en combos de taladros'
        })
        
        new_client = Cliente.objects.filter(dni_ruc='98765432').first()
        self.assertIsNotNone(new_client)
        self.assertRedirects(response, reverse('clientes:detalle', kwargs={'cliente_id': new_client.id}))
        self.assertEqual(new_client.nombre_completo, 'María Flores')
