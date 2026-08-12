"""
Módulo de respaldo: exportar e importar datos del sistema (solo superusuario).
"""
import io
import json
import os
import tempfile
from datetime import datetime

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods


EXCLUDED_APPS = [
    'contenttypes',
    'auth.permission',
    'admin.logentry',
    'sessions.session',
]


def _solo_superuser(request):
    return request.user.is_authenticated and request.user.is_superuser


@staff_member_required
def respaldo_view(request):
    """Redirige al módulo POS (menú lateral + reinicio operativo)."""
    if not _solo_superuser(request):
        raise PermissionDenied('Solo el superusuario puede gestionar respaldos.')
    return redirect('pos:hub_respaldo')


@staff_member_required
@require_http_methods(['GET'])
def exportar_base_datos(request):
    if not _solo_superuser(request):
        raise PermissionDenied('Solo el superusuario puede exportar.')

    buffer = io.StringIO()
    call_command(
        'dumpdata',
        '--natural-foreign',
        '--natural-primary',
        '--indent', '2',
        *[f'-e={app}' for app in EXCLUDED_APPS],
        stdout=buffer,
    )
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'elcharly_backup_{stamp}.json'
    response = HttpResponse(buffer.getvalue(), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@staff_member_required
@require_http_methods(['POST'])
def importar_base_datos(request):
    if not _solo_superuser(request):
        raise PermissionDenied('Solo el superusuario puede importar.')

    archivo = request.FILES.get('archivo')
    confirmar = request.POST.get('confirmar') == 'on'

    if not archivo:
        messages.error(request, 'Selecciona un archivo JSON de respaldo.')
        return redirect('pos:hub_respaldo')

    if not confirmar:
        messages.error(
            request,
            'Debes confirmar que entiendes que la importación puede sobrescribir datos.'
        )
        return redirect('pos:hub_respaldo')

    if not archivo.name.lower().endswith('.json'):
        messages.error(request, 'El archivo debe ser .json (exportado desde este módulo).')
        return redirect('pos:hub_respaldo')

    try:
        raw = archivo.read().decode('utf-8')
        json.loads(raw)
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as fh:
            fh.write(raw)
            tmp_path = fh.name
        try:
            call_command('loaddata', tmp_path, verbosity=0)
        finally:
            os.unlink(tmp_path)
        messages.success(request, 'Importación completada correctamente.')
    except Exception as exc:
        messages.error(request, f'Error al importar: {exc}')

    return redirect('pos:hub_respaldo')
