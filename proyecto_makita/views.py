"""Vistas de salud y errores HTTP (web pública vs sistema interno)."""
from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.sistema.internal_access import is_internal_path, is_staff_interno


def health(request):
    """Healthcheck liviano para router/monitor y failover 4G."""
    db_ok = False
    try:
        connection.ensure_connection()
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    payload = {
        'ok': db_ok,
        'db': 'ok' if db_ok else 'error',
        'app': 'elcharly',
    }
    return JsonResponse(payload, status=200 if db_ok else 503)


@require_GET
def robots_txt(request):
    """Impide indexar POS, admin y módulos internos."""
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /pos',
        'Disallow: /pos/',
        'Disallow: /admin/',
        'Disallow: /reportes/',
        'Disallow: /mantenimiento/',
        'Disallow: /clientes/',
        'Disallow: /cotizaciones/',
        'Disallow: /pagos/',
        'Disallow: /pedidos/staff/',
        'Disallow: /media/',
        '',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')


def _base_ctx(codigo, titulo, mensaje):
    return {
        'error_code': codigo,
        'error_title': titulo,
        'error_message': mensaje,
        'negocio': getattr(settings, 'NEGOCIO', {}),
        'cart_item_count': 0,
    }


def render_web_error(request, codigo, titulo, mensaje):
    """Error de tienda pública: sin POS, sin login, sin cerrar sesión."""
    template = {
        400: '400.html',
        403: '403.html',
        404: '404.html',
        500: '500.html',
    }.get(codigo, 'error.html')
    return render(request, template, _base_ctx(codigo, titulo, mensaje), status=codigo)


def render_pos_error(request, codigo, titulo, mensaje):
    """Error del sistema interno (solo personal autenticado)."""
    return render(
        request,
        'errors/pos.html',
        _base_ctx(codigo, titulo, mensaje),
        status=codigo,
    )


def _usar_error_pos(request) -> bool:
    path = getattr(request, 'path', '') or ''
    user = getattr(request, 'user', None)
    return is_internal_path(path) and is_staff_interno(user)


def _render_error(request, codigo, titulo, mensaje):
    if _usar_error_pos(request):
        return render_pos_error(request, codigo, titulo, mensaje)
    return render_web_error(request, codigo, titulo, mensaje)


def page_not_found(request, exception=None):
    return _render_error(
        request,
        404,
        'Página no encontrada',
        'La dirección que buscas no existe o fue movida. Revisa el enlace o vuelve al inicio.',
    )


def permission_denied(request, exception=None):
    # Si no es personal interno, no revelar que la ruta existe.
    if not is_staff_interno(getattr(request, 'user', None)):
        return page_not_found(request, exception)
    return _render_error(
        request,
        403,
        'Acceso no permitido',
        'No tienes permiso para ver esta sección.',
    )


def server_error(request):
    return _render_error(
        request,
        500,
        'Error del servidor',
        'Ocurrió un problema al procesar tu solicitud. Inténtalo de nuevo en unos minutos.',
    )


def bad_request(request, exception=None):
    return _render_error(
        request,
        400,
        'Solicitud incorrecta',
        'Los datos enviados no son válidos. Vuelve atrás e inténtalo de nuevo.',
    )
