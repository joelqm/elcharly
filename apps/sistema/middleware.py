"""
Middleware de auditoría: registra navegación en /pos/ (páginas HTML).
Acciones críticas se registran explícitamente con registrar_actividad().

También fuerza páginas de error con marca El Charly (incluso con DEBUG=True),
para que 404/403 no muestren la pantalla técnica de Django.
"""
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.utils.deprecation import MiddlewareMixin

from apps.sistema.activity import registrar_actividad

_SKIP_CONTAINS = (
    '/buscar',
    '/estado/',
    '/static/',
    '/media/',
)

_SKIP_BRANDED_PREFIXES = (
    '/static/',
    '/media/',
    '/health/',
    '/robots.txt',
)


# Infraestructura / sistema: no bloqueados por “web en construcción”
_CONSTRUCCION_ALLOW_PREFIXES = (
    '/admin/',
    '/pos/',
    '/cotizaciones/',
    '/cotizacion/publica/',
    '/clientes/',
    '/mantenimiento/',
    '/reportes/',
    '/pagos/',
    '/pedidos/staff/',
    '/static/',
    '/media/',
    '/health/',
)
_CONSTRUCCION_ALLOW_EXACT = (
    '/robots.txt',
    '/favicon.ico',
)


class TiendaEnConstruccionMiddleware(MiddlewareMixin):
    """
    Si WEB_PUBLICA_ACTIVA=False, la tienda online muestra “en construcción”.
    POS, admin, taller, cotizaciones y demás sistema interno siguen operativos.
    """

    def process_request(self, request):
        from django.conf import settings
        from django.shortcuts import render

        if getattr(settings, 'WEB_PUBLICA_ACTIVA', True):
            return None

        path = (request.path or '/').lower()
        if path in _CONSTRUCCION_ALLOW_EXACT:
            return None
        if any(path.startswith(p) for p in _CONSTRUCCION_ALLOW_PREFIXES):
            return None

        return render(
            request,
            'tienda/en_construccion.html',
            status=503,
            content_type='text/html; charset=utf-8',
        )


class NoIndexInternalMiddleware(MiddlewareMixin):
    """Evita que buscadores indexen POS y módulos internos."""

    def process_response(self, request, response):
        from apps.sistema.internal_access import is_internal_path

        if is_internal_path(request.path or ''):
            response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
        return response


class BrandedErrorPagesMiddleware(MiddlewareMixin):
    """Reemplaza respuestas 400/403/404 por plantillas con marca (web o POS)."""

    def process_response(self, request, response):
        status = getattr(response, 'status_code', None)
        if status not in (400, 403, 404):
            return response
        path = request.path or ''
        if any(path.startswith(p) for p in _SKIP_BRANDED_PREFIXES):
            return response
        # No tocar JSON/API ni descargas
        content_type = (response.get('Content-Type') or '').lower()
        if 'application/json' in content_type or 'application/octet-stream' in content_type:
            return response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return response
        # Si ya es nuestra plantilla, no re-renderizar
        try:
            body = response.content[:200].decode('utf-8', errors='ignore')
        except Exception:
            body = ''
        if 'error-wrap' in body or 'pos-error-card' in body or 'error-code' in body:
            return response

        from proyecto_makita import views as error_views

        if status == 404:
            return error_views.page_not_found(request)
        if status == 403:
            return error_views.permission_denied(request)
        return error_views.bad_request(request)


class ActivityLogMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        try:
            path = request.path or ''
            if not path.startswith('/pos/'):
                return response
            if any(s in path for s in _SKIP_CONTAINS):
                return response
            if not getattr(request, 'user', None) or not request.user.is_authenticated:
                return response
            if response.status_code >= 400:
                return response
            # Solo navegación GET de páginas (no AJAX JSON)
            if request.method != 'GET':
                return response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return response
            registrar_actividad(
                request,
                tipo='navegacion',
                accion=f'Ver {path}',
                detalle='',
            )
        except Exception:
            pass
        return response


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    registrar_actividad(
        request,
        usuario=user,
        tipo='login',
        accion='Inicio de sesión',
        detalle=f'Usuario {user.username} ingresó al sistema',
    )


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    registrar_actividad(
        request,
        usuario=user,
        tipo='logout',
        accion='Cierre de sesión',
        detalle=f'Usuario {getattr(user, "username", "?")} salió del sistema',
    )
