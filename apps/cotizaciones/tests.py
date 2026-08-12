from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
import datetime

from .models import Cotizacion, DetalleCotizacion
from apps.clientes.models import Cliente
from apps.tienda.models import Producto, Categoria
from apps.pedidos.models import Pedido, DetallePedido

User = get_user_model()

class CotizacionesTests(TestCase):
    def setUp(self):
        # Create users
        self.admin = User.objects.create_user(
            username='admin1',
            password='Password123!',
            rol=User.ROLE_ADMIN
        )
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
        
        # CRM client
        self.cliente = Cliente.objects.create(
            nombre_completo='Pedro Alcazar',
            tipo=Cliente.TIPO_PERSONA,
            dni_ruc='77665544',
            telefono='998877665',
            correo='pedro@gmail.com'
        )

        # Catalog spare part
        self.cat = Categoria.objects.create(nombre='Repuestos', slug='repuestos')
        self.repuesto = Producto.objects.create(
            codigo_articulo='CB-411',
            nombre='Escobillas Carbón CB-411',
            slug='escobillas-carbon-cb-411',
            precio_venta=Decimal('25.00'),
            stock=50,
            tipo=Producto.TIPO_REPUESTO,
            familia_sap='REPUESTOS',
            categoria=self.cat
        )

        self.client = Client()

    def test_cotizaciones_access_restriction(self):
        # Unauthenticated redirects
        response = self.client.get(reverse('cotizaciones:lista'))
        self.assertEqual(response.status_code, 302)
        
        # Cliente restricted (404 ocultando el sistema interno)
        self.client.login(username='cliente1', password='Password123!')
        response = self.client.get(reverse('cotizaciones:lista'))
        self.assertEqual(response.status_code, 404)
        self.client.logout()
        
        # Tecnico gets access (200)
        self.client.login(username='tecnico1', password='Password123!')
        response = self.client.get(reverse('cotizaciones:lista'))
        self.assertEqual(response.status_code, 200)
        self.client.logout()

    def test_cotizacion_correlative_and_calculations(self):
        # Create quote
        cot = Cotizacion.objects.create(
            cliente=self.cliente,
            modelo_equipo='Esmeril Angular M9507G',
            creado_por=self.tecnico
        )
        
        # Verify correlative format: STAEC-C-X
        self.assertTrue(cot.numero.startswith("STAEC-C-"))
        
        # Add catalog item
        item1 = DetalleCotizacion.objects.create(
            cotizacion=cot,
            repuesto=self.repuesto,
            cantidad=2,
            precio_unitario=Decimal('25.00')
        )
        self.assertEqual(item1.subtotal, Decimal('50.00'))
        
        # Add manual item (labor)
        item2 = DetalleCotizacion.objects.create(
            cotizacion=cot,
            descripcion_manual='Cambio de carbones y limpieza de inducido',
            cantidad=1,
            precio_unitario=Decimal('40.00')
        )
        self.assertEqual(item2.subtotal, Decimal('40.00'))
        
        # Refresh parent totals
        cot.refresh_from_db()
        self.assertEqual(cot.total, Decimal('90.00'))
        self.assertAlmostEqual(cot.subtotal, Decimal('76.27'), places=2)
        self.assertAlmostEqual(cot.igv, Decimal('13.73'), places=2)

    def test_cotizacion_nueva_form_submission(self):
        import json
        self.client.login(username='tecnico1', password='Password123!')
        
        items = [
            {'product_id': self.repuesto.id, 'descripcion': 'Escobillas Carbón CB-411', 'precio': 25.00, 'cantidad': 3},
            {'product_id': None, 'descripcion': 'Servicio técnico especializado', 'precio': 35.00, 'cantidad': 1}
        ]
        
        # Post new quote
        response = self.client.post(reverse('cotizaciones:nueva'), {
            'cliente': self.cliente.id,
            'modelo_equipo': 'Rotomartillo HR2470',
            'fecha_vencimiento': '2026-12-31',
            'notas': 'Cotización de prueba',
            'items_json': json.dumps(items)
        })
        
        # Verify redirect
        cot = Cotizacion.objects.filter(cliente=self.cliente).first()
        self.assertIsNotNone(cot)
        self.assertRedirects(response, reverse('cotizaciones:detalle', kwargs={'cotizacion_id': cot.id}))
        
        self.assertEqual(cot.total, Decimal('110.00'))
        self.assertEqual(cot.detalles.count(), 2)

    def test_generar_pdf_download(self):
        cot = Cotizacion.objects.create(
            cliente=self.cliente,
            modelo_equipo='HR2470',
            creado_por=self.tecnico
        )
        DetalleCotizacion.objects.create(
            cotizacion=cot,
            repuesto=self.repuesto,
            cantidad=1,
            precio_unitario=Decimal('25.00')
        )
        
        self.client.login(username='tecnico1', password='Password123!')
        response = self.client.get(reverse('cotizaciones:pdf', kwargs={'cotizacion_id': cot.id}))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response['Content-Disposition'].startswith('attachment; filename="cotizacion_'))

    def test_aprobar_cotizacion_and_convert_to_order(self):
        # Create quote with manual customer details
        cot = Cotizacion.objects.create(
            nombre_cliente_temporal='Cliente Manual Cotizado',
            dni_ruc_cliente_temporal='99887766551',
            correo_cliente_temporal='manual@gmail.com',
            telefono_cliente_temporal='999000111',
            modelo_equipo='HR2470',
            creado_por=self.tecnico
        )
        DetalleCotizacion.objects.create(
            cotizacion=cot,
            repuesto=self.repuesto,
            cantidad=2,
            precio_unitario=Decimal('25.00')
        )
        DetalleCotizacion.objects.create(
            cotizacion=cot,
            descripcion_manual='Mantenimiento General de Rotomartillo',
            cantidad=1,
            precio_unitario=Decimal('50.00')
        )
        # Total: (25 * 2) + 50 = 100.00
        
        self.client.login(username='tecnico1', password='Password123!')
        response = self.client.post(reverse('cotizaciones:aprobar', kwargs={'cotizacion_id': cot.id}))
        
        # Check redirect
        self.assertRedirects(response, reverse('cotizaciones:detalle', kwargs={'cotizacion_id': cot.id}))
        
        # Check quote is approved
        cot.refresh_from_db()
        self.assertEqual(cot.estado, Cotizacion.ESTADO_APROBADA)
        
        # Check customer was registered in CRM
        crm_client = Cliente.objects.filter(dni_ruc='99887766551').first()
        self.assertIsNotNone(crm_client)
        self.assertEqual(crm_client.nombre_completo, 'Cliente Manual Cotizado')
        
        # Check Pedido was created
        pedido = Pedido.objects.filter(cliente=crm_client, canal=Pedido.CANAL_COTIZACION).first()
        self.assertIsNotNone(pedido)
        self.assertEqual(pedido.estado, Pedido.ESTADO_PENDIENTE)
        self.assertEqual(pedido.total, Decimal('100.00'))
        
        # DetallePedido check:
        # Repuesto CB-411 (catalog product) and generic REP-MANUAL (for manual labor item)
        detalles_ped = DetallePedido.objects.filter(pedido=pedido)
        self.assertEqual(detalles_ped.count(), 2)
        
        det_catalog = detalles_ped.filter(producto=self.repuesto).first()
        self.assertIsNotNone(det_catalog)
        self.assertEqual(det_catalog.cantidad, 2)
        self.assertEqual(det_catalog.precio_unitario, Decimal('25.00'))
        
        # Generic product for manual item
        generic_prod = Producto.objects.get(codigo_articulo='REP-MANUAL')
        det_manual = detalles_ped.filter(producto=generic_prod).first()
        self.assertIsNotNone(det_manual)
        self.assertEqual(det_manual.cantidad, 1)
        self.assertEqual(det_manual.precio_unitario, Decimal('50.00'))

    def test_public_cotizacion_access(self):
        cot = Cotizacion.objects.create(
            cliente=self.cliente,
            modelo_equipo='HR2470',
            creado_por=self.tecnico
        )
        DetalleCotizacion.objects.create(
            cotizacion=cot,
            repuesto=self.repuesto,
            cantidad=1,
            precio_unitario=Decimal('25.00')
        )
        # Sin login de usuario -> retorna directamente el PDF generado
        response = self.client.get(reverse('cotizaciones:publica_ver', kwargs={'token': cot.token_publico}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_public_cotizacion_pdf(self):
        cot = Cotizacion.objects.create(
            cliente=self.cliente,
            modelo_equipo='HR2470',
            creado_por=self.tecnico
        )
        DetalleCotizacion.objects.create(
            cotizacion=cot,
            repuesto=self.repuesto,
            cantidad=1,
            precio_unitario=Decimal('25.00')
        )
        # Sin login de usuario
        response = self.client.get(reverse('cotizaciones:publica_pdf', kwargs={'token': cot.token_publico}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
