from django.core.management.base import BaseCommand
from decimal import Decimal
from apps.tienda.models import Categoria, Producto


class Command(BaseCommand):
    help = 'Crea categorías y productos demo Makita (herramientas/accesorios, sin repuestos web).'

    def handle(self, *args, **options):
        cat_herr, _ = Categoria.objects.get_or_create(nombre='Herramientas')
        cat_acc, _ = Categoria.objects.get_or_create(nombre='Accesorios')
        cat_rep, _ = Categoria.objects.get_or_create(nombre='Repuestos')

        # Repuestos no se venden en la tienda web
        Producto.objects.filter(tipo=Producto.TIPO_REPUESTO).update(activo=False)
        Producto.objects.filter(familia_sap__iexact='REPUESTOS').update(activo=False)
        Producto.objects.filter(categoria=cat_rep).update(activo=False)

        demos = [
            {
                'codigo_articulo': 'DHP484Z',
                'nombre': 'Taladro Atornillador Percutor 18V LXT',
                'descripcion': (
                    'Taladro percutor Makita 18V LXT (solo cuerpo). Ideal para obra y taller. '
                    'Compatible con baterías LXT. Recojo en tienda STA El Charly — Galería ASPYME.'
                ),
                'familia_sap': 'EQUIPOS',
                'tipo': Producto.TIPO_HERRAMIENTA,
                'modelo': 'DHP484Z',
                'voltaje': '18V LXT',
                'precio_venta': Decimal('899.00'),
                'stock': 8,
                'categoria': cat_herr,
            },
            {
                'codigo_articulo': 'B-49069',
                'nombre': 'Juego de Brocas para Metal HSS 19 pzas',
                'descripcion': (
                    'Set de brocas Makita para metal. Accesorio original para perforación precisa. '
                    'Disponible para recojo en nuestra tienda de Arequipa.'
                ),
                'familia_sap': 'ACCESORIOS',
                'tipo': Producto.TIPO_ACCESORIO,
                'modelo': 'B-49069',
                'voltaje': '',
                'precio_venta': Decimal('89.90'),
                'stock': 25,
                'categoria': cat_acc,
            },
            {
                'codigo_articulo': 'DGA452Z',
                'nombre': 'Amoladora Angular 18V LXT 115 mm',
                'descripcion': (
                    'Amoladora Makita 18V LXT (solo cuerpo). Potencia profesional para corte y desbaste. '
                    'Recojo en tienda El Charly Makita, Arequipa.'
                ),
                'familia_sap': 'EQUIPOS',
                'tipo': Producto.TIPO_HERRAMIENTA,
                'modelo': 'DGA452Z',
                'voltaje': '18V LXT',
                'precio_venta': Decimal('649.00'),
                'stock': 6,
                'categoria': cat_herr,
            },
        ]

        for data in demos:
            obj, created = Producto.objects.update_or_create(
                codigo_articulo=data['codigo_articulo'],
                defaults={**data, 'activo': True, 'marca': 'Makita', 'precio_costo': Decimal('0.00')},
            )
            self.stdout.write(
                self.style.SUCCESS(f"{'Creado' if created else 'Actualizado'}: {obj.codigo_articulo}")
            )

        self.stdout.write(self.style.NOTICE('Listo. Repuestos web desactivados; solo herramientas y accesorios.'))
