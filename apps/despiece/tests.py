from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.despiece.models import DespieceEquipo, DespieceItem
from apps.tienda.models import Producto

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
            descripcion='MONTAJE DE LA ARMADURA 220V',
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
