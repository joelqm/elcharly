from django.core.management.base import BaseCommand

from apps.sistema.reset_operativo import reiniciar_data_operativa


class Command(BaseCommand):
    help = (
        'Borra data operativa de pruebas (ventas, pagos, caja, movimientos, OT, cotizaciones) '
        'y pone stock en 0. Conserva productos, clientes, usuarios, sedes y correlativo OT.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Confirma el borrado sin preguntar (obligatorio en scripts).',
        )
        parser.add_argument(
            '--keep-import-logs',
            action='store_true',
            help='Conserva historial de importaciones Excel.',
        )

    def handle(self, *args, **options):
        if not options['yes']:
            self.stderr.write(
                self.style.ERROR('Abortado. Usa --yes para confirmar (acción irreversible).')
            )
            return

        stats = reiniciar_data_operativa(
            wipe_import_logs=not options['keep_import_logs'],
        )
        self.stdout.write(self.style.SUCCESS('Data operativa reiniciada (clientes y correlativo OT intactos).'))
        for k, v in stats.items():
            self.stdout.write(f'  {k}: {v}')
