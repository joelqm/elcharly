"""Crea/actualiza despiece HR5212C con las 2 páginas de diagrama (capturas MSI)."""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.conf import settings

from apps.despiece.models import DespieceEquipo, DespiecePagina


class Command(BaseCommand):
    help = 'Carga diagramas HR5212C (páginas 1 y 2) desde media/despieces/diagramas/'

    def handle(self, *args, **options):
        # Preferir resources/ (versionado) y caer a media/
        candidates = [
            Path(settings.BASE_DIR) / 'resources' / 'despieces' / 'HR5212C',
            Path(settings.MEDIA_ROOT) / 'despieces' / 'diagramas',
        ]
        p1 = p2 = None
        for folder in candidates:
            a, b = folder / 'p1.png', folder / 'p2.png'
            if not a.exists():
                a, b = folder / 'hr5212c_p1.png', folder / 'hr5212c_p2.png'
            if a.exists() and b.exists():
                p1, p2 = a, b
                break
        if not p1 or not p2:
            self.stderr.write(
                'Faltan p1.png/p2.png en resources/despieces/HR5212C/ '
                'o hr5212c_p1/p2.png en media/despieces/diagramas/'
            )
            return

        despiece, _ = DespieceEquipo.objects.get_or_create(
            modelo='HR5212C',
            defaults={
                'nombre_equipo': 'Martillo Rotativo HR5212C',
                'archivo_pdf': '',
                'total_partes': 0,
            },
        )
        despiece.nombre_equipo = 'Martillo Rotativo HR5212C'
        with p1.open('rb') as fh:
            despiece.imagen_diagrama.save('hr5212c_p1.png', File(fh), save=False)
        despiece.save()

        for num, path in ((1, p1), (2, p2)):
            pagina, _ = DespiecePagina.objects.get_or_create(
                despiece=despiece, numero=num,
            )
            with path.open('rb') as fh:
                pagina.imagen.save(path.name, File(fh), save=True)

        self.stdout.write(self.style.SUCCESS(
            f'HR5212C listo · {despiece.paginas.count()} página(s). '
            'Sube el PDF Makita a resources/despieces/ y ejecuta «Escanear» '
            'para cargar la lista de repuestos; luego mapea hotspots en el visor.'
        ))
