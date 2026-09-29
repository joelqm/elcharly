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

        self.assertTrue(ticket.numero_serie.startswith('R001-'))
        pedido = Pedido.objects.get(id=ticket.pedido_id)
        self.assertEqual(pedido.canal, Pedido.CANAL_POS)
        self.assertEqual(pedido.estado, Pedido.ESTADO_ENTREGADO)
        self.assertFalse(pedido.es_historica)
        self.assertEqual(pedido.caja_sesion_id, sesion.id)
        self.assertEqual(pedido.numero_pedido, ticket.numero_serie)

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

    def test_hub_producto_editar_precio_lista(self):
        self.client.login(username='cajero1', password='Password123!')
        url = reverse('pos:hub_producto_editar', kwargs={'producto_id': self.prod1.id})
        response = self.client.post(url, {
            'accion': 'guardar',
            'codigo_articulo': self.prod1.codigo_articulo,
            'nombre': self.prod1.nombre,
            'tipo': self.prod1.tipo,
            'precio_venta': '420.50',
            'precio_con_igv': '496.19',
            'precio_costo': '300.00',
            'stock': '10',
            'stock_web': '0',
            'activo': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.precio_venta, Decimal('420.50'))
        self.assertEqual(self.prod1.precio_costo, Decimal('300.00'))

    def test_hub_producto_editar_precio_desde_igv(self):
        self.client.login(username='cajero1', password='Password123!')
        url = reverse('pos:hub_producto_editar', kwargs={'producto_id': self.prod1.id})
        response = self.client.post(url, {
            'accion': 'guardar',
            'codigo_articulo': self.prod1.codigo_articulo,
            'nombre': self.prod1.nombre,
            'tipo': self.prod1.tipo,
            'precio_con_igv': '590.00',
            'precio_costo': '0',
            'stock': '10',
            'stock_web': '0',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.precio_venta, Decimal('500.00'))

    def test_hub_producto_editar_muestra_precios_en_formulario(self):
        self.client.login(username='cajero1', password='Password123!')
        url = reverse('pos:hub_producto_editar', kwargs={'producto_id': self.prod1.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="precio_venta"')
        self.assertContains(response, f'value="{self.prod1.precio_venta}"')
        self.assertContains(response, 'id="precio-con-igv"')

    def test_hub_producto_editar_no_borra_precio_si_campo_vacio(self):
        self.client.login(username='cajero1', password='Password123!')
        url = reverse('pos:hub_producto_editar', kwargs={'producto_id': self.prod1.id})
        response = self.client.post(url, {
            'accion': 'guardar',
            'codigo_articulo': self.prod1.codigo_articulo,
            'nombre': self.prod1.nombre,
            'tipo': self.prod1.tipo,
            'precio_venta': '',
            'precio_con_igv': '',
            'precio_costo': '',
            'stock': '10',
            'stock_web': '0',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.precio_venta, Decimal('350.00'))

    def test_anular_venta_historica_no_devuelve_stock(self):
        self.client.login(username='cajero1', password='Password123!')
        CajaSesion.objects.create(
            cajero=self.cajero,
            sede=self.sede,
            monto_apertura=Decimal('100.00'),
            estado=CajaSesion.ESTADO_ABIERTA,
        )
        ayer = timezone.localdate() - timedelta(days=2)
        stock_antes = self.prod1.stock
        response = self.client.post(
            reverse('pos:registrar_venta'),
            data={
                'cliente_varios': True,
                'metodo_pago': 'efectivo',
                'tipo_comprobante': 'ticket',
                'fecha_venta': ayer.isoformat(),
                'items': [
                    {'id': self.prod1.id, 'cantidad': 3, 'precio': 350.00},
                ],
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        pedido = Pedido.objects.get(id=TicketPOS.objects.get(
            id=response.json()['ticket_id'],
        ).pedido_id)
        self.assertTrue(pedido.es_historica)
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.stock, stock_antes)

        anular = self.client.post(
            reverse('pos:hub_pedido_detalle', args=[pedido.id]),
            {'accion': 'anular_venta'},
        )
        self.assertEqual(anular.status_code, 302)
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.stock, stock_antes)

    def test_registrar_apartado_pos_sin_descontar_stock(self):
        self.client.login(username='cajero1', password='Password123!')
        CajaSesion.objects.create(
            cajero=self.cajero,
            sede=self.sede,
            monto_apertura=Decimal('100.00'),
            estado=CajaSesion.ESTADO_ABIERTA,
        )
        stock_antes = self.prod2.stock
        response = self.client.post(
            reverse('pos:registrar_venta'),
            data={
                'cliente_varios': True,
                'metodo_pago': 'efectivo',
                'modo_venta': 'pedido',
                'anticipo': '100.00',
                'tipo_comprobante': 'ticket',
                'items': [
                    {'id': self.prod2.id, 'cantidad': 1, 'precio': 620.00},
                ],
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['modo'], 'apartado')

        self.prod2.refresh_from_db()
        self.assertEqual(self.prod2.stock, stock_antes)

        pedido = Pedido.objects.get(id=data['pedido_id'])
        self.assertEqual(pedido.estado, Pedido.ESTADO_PENDIENTE)
        self.assertEqual(pedido.monto_pagado, Decimal('100.00'))
        self.assertEqual(pedido.saldo_pendiente, Decimal('520.00'))

    def test_busqueda_sin_tildes_encuentra_producto(self):
        self.client.login(username='cajero1', password='Password123!')
        carbon = Producto.objects.create(
            codigo_articulo='CB-GEN',
            nombre='CARBÓN GENÉRICO',
            slug='carbon-generico',
            precio_venta=Decimal('12.00'),
            stock=5,
            categoria=self.cat,
            activo=True,
        )
        self.assertIn('carbon', carbon.nombre_busqueda)
        response = self.client.get(reverse('pos:buscar_productos') + '?q=carbon generico')
        self.assertEqual(response.status_code, 200)
        ids = [p['id'] for p in response.json()['productos']]
        self.assertIn(carbon.id, ids)

    def test_consulta_documento_prioriza_crm(self):
        Cliente.objects.create(
            nombre_completo='Rosa Paredes',
            dni_ruc='45892156',
            telefono='987654321',
            direccion='Av. Ejército 100',
        )
        self.client.login(username='cajero1', password='Password123!')
        response = self.client.get(
            reverse('pos:hub_consulta_documento'),
            {'numero': '45892156'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['fuente'], 'crm')
        self.assertEqual(data['nombre'], 'Rosa Paredes')
        self.assertEqual(data['telefono'], '987654321')

    def test_historial_precios_incluye_cotizaciones(self):
        from apps.cotizaciones.models import Cotizacion, DetalleCotizacion
        from apps.tienda.precios import con_igv

        self.client.login(username='cajero1', password='Password123!')
        cot = Cotizacion.objects.create(
            nombre_cliente_temporal='Cliente prueba',
            dni_ruc_cliente_temporal='00000000',
            creado_por=self.cajero,
        )
        DetalleCotizacion.objects.create(
            cotizacion=cot,
            repuesto=self.prod1,
            cantidad=2,
            precio_unitario=Decimal('399.00'),
        )
        url = reverse('pos:hub_historial_precios_datos', args=[self.prod1.id])
        response = self.client.get(url + '?dias=365')
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['resumen']['n_cotizaciones'], 1)
        self.assertEqual(data['cotizaciones'][0]['precio'], 399.0)
        self.assertEqual(data['cotizaciones'][0]['numero'], cot.numero)
        self.assertAlmostEqual(data['producto']['lista_con_igv'], float(con_igv(self.prod1.precio_venta)))

    def test_correlativos_concurrentes_no_duplican(self):
        from apps.pos.correlativos import siguiente_numero, SERIE_RECIBO
        from apps.pos.models import CorrelativoSerie

        a = siguiente_numero(SERIE_RECIBO)
        b = siguiente_numero(SERIE_RECIBO)
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith('R001-'))
        self.assertTrue(b.startswith('R001-'))
        n_a = int(a.split('-')[1])
        n_b = int(b.split('-')[1])
        self.assertEqual(n_b, n_a + 1)
        row = CorrelativoSerie.objects.get(serie=SERIE_RECIBO)
        self.assertEqual(row.ultimo, n_b)

    def test_editar_datos_generales_fecha_y_cliente(self):
        self.client.login(username='cajero1', password='Password123!')
        sesion = CajaSesion.objects.create(
            cajero=self.cajero,
            sede=self.sede,
            monto_apertura=Decimal('100.00'),
            estado=CajaSesion.ESTADO_ABIERTA,
        )
        response = self.client.post(
            reverse('pos:registrar_venta'),
            data={
                'cliente_varios': True,
                'metodo_pago': 'efectivo',
                'tipo_comprobante': 'ticket',
                'items': [{'id': self.prod1.id, 'cantidad': 1, 'precio': 350.00}],
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        ticket = TicketPOS.objects.get(id=response.json()['ticket_id'])
        pedido = ticket.pedido
        ayer = timezone.localdate() - timedelta(days=1)

        edit = self.client.post(
            reverse('pos:hub_pedido_detalle', args=[pedido.id]),
            {
                'accion': 'editar_datos_generales',
                'cliente_dni_ruc': '12345678',
                'cliente_nombre': 'Cliente Corregido',
                'cliente_telefono': '999888777',
                'cliente_correo': '',
                'cliente_direccion': 'Calle 1',
                'fecha_venta': ayer.isoformat(),
                'metodo_pago': 'yape',
            },
        )
        self.assertEqual(edit.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.cliente.dni_ruc, '12345678')
        self.assertEqual(pedido.cliente.nombre_completo, 'Cliente Corregido')
        self.assertEqual(timezone.localdate(pedido.fecha_pedido), ayer)
        self.assertTrue(pedido.es_historica)
        self.assertIsNone(pedido.caja_sesion_id)
        pago = Pago.objects.filter(pedido=pedido, estado=Pago.ESTADO_APROBADO).first()
        self.assertEqual(pago.metodo, Pago.METODO_YAPE)
        # Stock no se toca al editar fecha
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.stock, 9)


