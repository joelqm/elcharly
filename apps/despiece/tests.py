from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.despiece.models import DespieceEquipo, DespieceItem
from apps.despiece.services import (
    es_sku_makita,
    parse_page_spec,
    _parse_linea_pieza,
    normalizar_puntos_silueta,
    centro_radio_silueta,
)
from apps.tienda.models import Producto


class ParseDespieceHelpersTests(SimpleTestCase):
    def test_parse_page_spec_comas_y_rangos(self):
        self.assertEqual(parse_page_spec('1,2,5-7', 10), [0, 1, 4, 5, 6])
        self.assertEqual(parse_page_spec('', 10), [])
        self.assertEqual(parse_page_spec('99', 10), [])
        self.assertEqual(parse_page_spec('3-1', 5), [0, 1, 2])

    def test_sku_makita_no_indice(self):
        self.assertTrue(es_sku_makita('265995-6'))
        self.assertTrue(es_sku_makita('511A48-8'))
        self.assertTrue(es_sku_makita('DA00000156'))
        self.assertFalse(es_sku_makita('CONTENIDO'))
        self.assertIsNone(_parse_linea_pieza('1 CONTENIDO ............... 2'))
        row = _parse_linea_pieza('016 511A48-8 MONTAJE DE LA ARMADURA 1')
        self.assertEqual(row['codigo_articulo'], '511A48-8')
        self.assertEqual(row['posicion'], '016')
        sub = _parse_linea_pieza('126-1 922359-4 PERNO DE CABEZA HUECA 1')
        self.assertEqual(sub['posicion'], '126-1')
        self.assertEqual(sub['codigo_articulo'], '922359-4')
        acc = _parse_linea_pieza('194984-3 CARBON CB-132')
        self.assertEqual(acc['posicion'], '')
        self.assertEqual(acc['codigo_articulo'], '194984-3')
        interno = _parse_linea_pieza('C10 213017-8 ANILLO O-RING 55 1')
        self.assertEqual(interno['posicion'], 'C10')
        self.assertEqual(interno['codigo_articulo'], '213017-8')

    def test_grupos_subpieza_e_internos(self):
        from types import SimpleNamespace
        from apps.despiece.services import asignar_grupos_despiece, clave_orden_item_agrupado
        items = [
            SimpleNamespace(posicion='013', id=1),
            SimpleNamespace(posicion='013-1', id=2),
            SimpleNamespace(posicion='015', id=3),
            SimpleNamespace(posicion='C10', id=4),
            SimpleNamespace(posicion='', id=5),
            SimpleNamespace(posicion='016', id=6),
            SimpleNamespace(posicion='', id=7),
        ]
        asignar_grupos_despiece(items)
        self.assertEqual(items[0].grupo, '013')
        self.assertEqual(items[1].grupo, '013')
        self.assertEqual(items[1].tipo_fila, 'sub')
        self.assertEqual(items[3].grupo, '015')
        self.assertEqual(items[3].tipo_fila, 'interno')
        self.assertEqual(items[4].grupo, '015')
        self.assertEqual(items[4].tipo_fila, 'interno')
        self.assertEqual(items[6].tipo_fila, 'acc')
        items.sort(key=clave_orden_item_agrupado)
        self.assertEqual([i.posicion for i in items], ['013', '013-1', '015', 'C10', '', '016', ''])
        self.assertEqual(items[4].tipo_fila, 'interno')
        self.assertEqual(items[-1].tipo_fila, 'acc')

    def test_orden_posicion_subpieza(self):
        from apps.despiece.services import clave_orden_posicion
        ordered = sorted(['126-1', '2', '126', '001', 'A', ''], key=clave_orden_posicion)
        self.assertEqual(ordered, ['001', '2', '126', '126-1', 'A', ''])

    def test_silueta_poligono(self):
        pts = normalizar_puntos_silueta([{'x': 10, 'y': 10}, [20, 10], {'x': 15, 'y': 20}])
        self.assertEqual(len(pts), 3)
        cx, cy, r = centro_radio_silueta(pts)
        self.assertAlmostEqual(cx, 15.0)
        self.assertGreater(r, 0)

User = get_user_model()


class DespieceTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='cajero_test',
            password='password123',
            is_staff=True,
            is_superuser=True,
            rol='vendedor',
        )
        self.client.login(username='cajero_test', password='password123')

        self.producto = Producto.objects.create(
            codigo_articulo='511A48-8',
            nombre='MONTAJE DE LA ARMADURA 220V',
            precio_venta=100.00,
            tipo=Producto.TIPO_REPUESTO,
            stock=5,
        )

        self.despiece = DespieceEquipo.objects.create(
            modelo='GA4590',
            nombre_equipo='ESMERILADORA ANGULAR',
            archivo_pdf='GA4590.pdf',
            total_partes=1,
        )

        self.item = DespieceItem.objects.create(
            despiece=self.despiece,
            posicion='016',
            codigo_articulo='511A48-8',
            descripcion='MONTAJE ARMADURA PDF',
            cantidad=1,
            producto=self.producto,
        )

    def test_despiece_lista_view(self):
        response = self.client.get(reverse('despiece:despiece_lista'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'GA4590')

    def test_despiece_visor_view(self):
        response = self.client.get(reverse('despiece:despiece_visor', kwargs={'modelo': 'GA4590'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '511A48-8')
        self.assertContains(response, 'MONTAJE DE LA ARMADURA 220V')
        self.assertContains(response, 'MONTAJE ARMADURA PDF')
        self.assertContains(response, 'nombre_guia')
        self.assertContains(response, 'ZOOM_MAX = 2.5')
        self.assertContains(response, 'ZOOM_STEP = 0.15')
        self.assertContains(response, 'Dónde se usa')
        self.assertContains(response, 'Cambiar PDF')
        self.assertContains(response, 'Lista de despieces')
        self.assertContains(response, 'Quitar marca')
        self.assertContains(response, 'Trazar silueta')
        self.assertContains(response, '"stock_disponible": 5')
        self.assertContains(response, 'stroke-width: 2.7px')

    def test_donde_se_usa_sku_en_otros_equipos(self):
        otro = DespieceEquipo.objects.create(
            modelo='HR5212C',
            nombre_equipo='MARTILLO ROTATIVO',
            archivo_pdf='HR5212C.pdf',
            total_partes=1,
        )
        DespieceItem.objects.create(
            despiece=otro,
            posicion='016',
            codigo_articulo='511A48-8',
            descripcion='MONTAJE ARMADURA PDF',
            cantidad=1,
        )
        url = reverse('despiece:despiece_donde_se_usa', kwargs={'modelo': 'GA4590'})
        response = self.client.get(url, {'sku': '511A48-8'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        modelos = {u['modelo'] for u in data['usos']}
        self.assertEqual(modelos, {'GA4590', 'HR5212C'})
        actual = next(u for u in data['usos'] if u['modelo'] == 'GA4590')
        self.assertTrue(actual['es_actual'])
