from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from .models import Categoria, Producto
from .precios import comparar_vs_lista, resumir_vs_lista, grupo_descuento

class TiendaModelsTestCase(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Herramientas Inalámbricas")

    def test_categoria_slug_generation(self):
        self.assertEqual(self.categoria.slug, "herramientas-inalambricas")

    def test_producto_slug_generation(self):
        producto = Producto.objects.create(
            codigo_articulo="DHP484Z",
            nombre="Taladro Percutor 18V LXT",
            familia_sap="EQUIPOS",
            precio_venta=850.50,
            categoria=self.categoria
        )
        self.assertEqual(producto.slug, "taladro-percutor-18v-lxt-dhp484z")
        self.assertEqual(producto.marca, "Makita")

class TiendaViewsTestCase(TestCase):
    def setUp(self):
        self.cat_repuestos = Categoria.objects.create(nombre="Repuestos")
        self.cat_accesorios = Categoria.objects.create(nombre="Accesorios")
        self.cat_herramientas = Categoria.objects.create(nombre="Herramientas")

        self.prod1 = Producto.objects.create(
            codigo_articulo="001118100",
            nombre="CASQUILLO DE MOTOR",
            familia_sap="REPUESTOS",
            precio_venta=15.00,
            categoria=self.cat_repuestos,
            voltaje="220V"
        )
        self.prod2 = Producto.objects.create(
            codigo_articulo="122256-6",
            nombre="PORTA GUIA CIRCULAR 3612-BR",
            familia_sap="ACCESORIOS",
            precio_venta=113.40,
            categoria=self.cat_accesorios,
            modelo="3612-BR",
            mostrar_en_web=True,
        )
        self.prod3 = Producto.objects.create(
            codigo_articulo="DHP484Z",
            nombre="Taladro Percutor 18V",
            familia_sap="EQUIPOS",
            precio_venta=850.00,
            categoria=self.cat_herramientas,
            modelo="DHP484",
            mostrar_en_web=True,
        )
        # Importado pero no publicado en web
        self.prod_oculto = Producto.objects.create(
            codigo_articulo="HIDDEN99",
            nombre="Sierra Circular Oculta",
            familia_sap="EQUIPOS",
            precio_venta=500.00,
            categoria=self.cat_herramientas,
            mostrar_en_web=False,
        )

    def test_catalogo_completo(self):
        response = self.client.get('/catalogo/')
        self.assertEqual(response.status_code, 200)
        # Repuestos no se venden por la web
        self.assertNotContains(response, "CASQUILLO DE MOTOR")
        self.assertContains(response, "PORTA GUIA CIRCULAR 3612-BR")
        self.assertContains(response, "Taladro Percutor 18V")
        # Sin marcar mostrar_en_web no aparece
        self.assertNotContains(response, "Sierra Circular Oculta")
        self.assertNotContains(response, "HIDDEN99")

    def test_catalogo_redirect_desde_tienda(self):
        response = self.client.get('/tienda/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith('/catalogo/'))

    def test_catalogo_busqueda(self):
        response = self.client.get('/catalogo/?q=Taladro')
        self.assertContains(response, "DHP484Z")
        self.assertNotContains(response, "122256-6")

        response = self.client.get('/catalogo/?q=122256-6')
        self.assertContains(response, "PORTA GUIA CIRCULAR 3612-BR")
        self.assertNotContains(response, "DHP484Z")

        # Repuestos no aparecen aunque busques por nombre
        response = self.client.get('/catalogo/?q=CASQUILLO')
        self.assertNotContains(response, "001118100")

    def test_catalogo_filtrado(self):
        response = self.client.get('/catalogo/?familia=ACCESORIOS')
        self.assertContains(response, "122256-6")
        self.assertNotContains(response, "DHP484Z")

        response = self.client.get(f'/catalogo/?categoria={self.cat_herramientas.slug}')
        self.assertContains(response, "DHP484Z")
        self.assertNotContains(response, "122256-6")

from django.contrib.auth import get_user_model

class AdminViewsTestCase(TestCase):
    def setUp(self):
        Usuario = get_user_model()
        self.admin_user = Usuario.objects.create_superuser(
            username='admin_test_unfold',
            password='password123',
            email='admin@test.com'
        )

    def test_admin_add_categoria_view(self):
        self.client.login(username='admin_test_unfold', password='password123')
        response = self.client.get('/admin/tienda/categoria/add/')
        self.assertEqual(response.status_code, 200)


class CompararVsListaTests(SimpleTestCase):
    def test_igual_a_lista_con_igv(self):
        row = comparar_vs_lista('118.00', '100.00', 1)
        self.assertEqual(row['estado'], 'igual')
        self.assertEqual(row['diferencia'], 0)

    def test_sobre_lista_por_cantidad(self):
        row = comparar_vs_lista('130.00', '100.00', 2)
        self.assertEqual(row['estado'], 'sobre')
        self.assertEqual(row['lista_linea'], 236)
        self.assertEqual(row['diferencia'], 24)

    def test_bajo_lista(self):
        row = comparar_vs_lista('100.00', '100.00', 1)
        self.assertEqual(row['estado'], 'bajo')
        self.assertEqual(row['diferencia'], -18)

    def test_sin_lista_no_entra_al_resumen(self):
        resumen = resumir_vs_lista([
            comparar_vs_lista('50.00', '0', 1),
            comparar_vs_lista('118.00', '100.00', 1),
        ])
        self.assertEqual(resumen['sin_lista'], 1)
        self.assertEqual(resumen['con_lista'], 1)
        self.assertEqual(resumen['diferencia'], 0)
        self.assertEqual(resumen['estado'], 'igual')

    def test_descuento_sobre_lista_con_igv(self):
        row = comparar_vs_lista('100.00', '100.00', 1, descuento_pct='20')
        self.assertEqual(row['lista_con_igv'], 118)
        self.assertEqual(row['referencia_linea'], Decimal('94.40'))
        self.assertEqual(row['diferencia'], Decimal('5.60'))
        self.assertEqual(row['estado'], 'sobre')

    def test_grupo_de_descuento(self):
        self.assertEqual(grupo_descuento('repuesto', 'EQUIPOS'), 'repuesto')
        self.assertEqual(grupo_descuento('herramienta', 'REPUESTOS'), 'equipo')
        self.assertEqual(grupo_descuento('accesorio', ''), 'equipo')
        self.assertEqual(grupo_descuento('servicio', ''), '')

