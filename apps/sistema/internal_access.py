"""
Acceso al sistema interno (POS / taller / CRM).

- Visitantes sin sesión → login propio del POS (mismos usuarios que admin).
- Cuentas sin rol interno → 404 de tienda (no revelar el sistema).
- Buscadores: robots.txt + X-Robots-Tag noindex.
"""
from urllib.parse import quote

from django.shortcuts import redirect
from django.urls import reverse

INTERNAL_PATH_PREFIXES = (
    '/pos/',
    '/admin/',
    '/reportes/',
    '/mantenimiento/',
    '/clientes/',
    '/cotizaciones/',
    '/pagos/',
    '/pedidos/staff/',
)

PUBLIC_INTERNAL_PATHS = (
    '/pos/login/',
)


def is_internal_path(path: str) -> bool:
    path = (path or '').lower()
    if path.startswith('/cotizacion/publica/'):
        return False
    if not path.endswith('/') and path.count('/') == 1:
        path = path + '/'
    return any(path.startswith(p) for p in INTERNAL_PATH_PREFIXES)


def is_staff_interno(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    rol = getattr(user, 'rol', None)
    roles = []
    for attr in ('ROLE_ADMIN', 'ROLE_VENDEDOR', 'ROLE_TECNICO'):
        val = getattr(user, attr, None)
        if val:
            roles.append(val)
    if not roles:
        roles = ['admin', 'vendedor', 'tecnico']
    return rol in roles


def puede_usar_pos(user) -> bool:
    """Cajero / admin (punto de venta)."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    rol = getattr(user, 'rol', None)
    return rol in (
        getattr(user, 'ROLE_ADMIN', 'admin'),
        getattr(user, 'ROLE_VENDEDOR', 'vendedor'),
    )


def ocultar_sistema_interno(request):
    """404 de tienda pública: no menciona POS, login ni admin."""
    from proyecto_makita.views import render_web_error

    return render_web_error(
        request,
        404,
        'Página no encontrada',
        'La dirección que buscas no existe o fue movida. Revisa el enlace o vuelve al inicio.',
    )


def redirect_pos_login(request):
    """Manda al login del POS conservando la URL destino."""
    login_url = reverse('pos:login')
    nxt = request.get_full_path() or '/pos/inicio/'
    if nxt.startswith(login_url):
        return redirect(login_url)
    return redirect(f'{login_url}?next={quote(nxt, safe="/?=&")}')
