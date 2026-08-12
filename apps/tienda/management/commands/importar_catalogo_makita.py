from django.core.management.base import BaseCommand, CommandError
from pathlib import Path

from apps.tienda.importers.makita_excel import importar_catalogo_makita
from apps.tienda.models import ImportacionCatalogo, Producto


class Command(BaseCommand):
    help = (
        'Importa catálogo Makita desde Excel (hoja Lista de Productos). '
        'No elimina productos: solo inserta o actualiza.'
    )

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str, help='Ruta al .xlsx')
        parser.add_argument(
            '--tipo',
            choices=['auto', 'repuestos', 'accesorios_equipos'],
            default='auto',
        )
        parser.add_argument(
            '--limpiar-demo',
            action='store_true',
            help='Elimina productos demo no usados en pedidos (solo limpieza inicial).',
        )

    def handle(self, *args, **options):
        path = Path(options['archivo'])
        if not path.exists():
            raise CommandError(f'No existe el archivo: {path}')

        if options['limpiar_demo']:
            from apps.pedidos.models import DetallePedido
            usados = set(DetallePedido.objects.values_list('producto_id', flat=True))
            qs = Producto.objects.exclude(id__in=usados) if usados else Producto.objects.all()
            n, _ = qs.delete()
            self.stdout.write(self.style.WARNING(f'Productos demo eliminados: {n}'))

        with path.open('rb') as fh:
            imp = importar_catalogo_makita(
                file_obj=fh,
                archivo_nombre=path.name,
                tipo_archivo=options['tipo'],
                usuario=None,
                en_background=False,
            )

        self.stdout.write(self.style.SUCCESS(
            f'OK {path.name}: filas={imp.total_filas} '
            f'nuevos={imp.total_nuevos} actualizados={imp.total_actualizados} '
            f'sin_cambio={imp.total_sin_cambio} log_id={imp.id} estado={imp.estado}'
        ))
