from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Procesa una ImportacionCatalogo por ID (pensado para segundo plano).'

    def add_arguments(self, parser):
        parser.add_argument('importacion_id', type=int)

    def handle(self, *args, **options):
        from apps.tienda.importers.makita_excel import procesar_importacion

        pk = options['importacion_id']
        self.stdout.write(f'Procesando importación #{pk}…')
        procesar_importacion(pk)
        self.stdout.write(self.style.SUCCESS(f'Importación #{pk} finalizada.'))
