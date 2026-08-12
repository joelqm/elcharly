"""Utilidades de auditoría / log de actividad."""
from __future__ import annotations


def registrar_actividad(
    request=None,
    *,
    usuario=None,
    tipo: str = 'otro',
    accion: str,
    detalle: str = '',
    ruta: str = '',
    metodo: str = '',
):
    """Guarda un LogActividad. Seguro ante fallos (no rompe la petición)."""
    try:
        from apps.sistema.models import LogActividad

        user = usuario
        ip = None
        if request is not None:
            if user is None and getattr(request, 'user', None) and request.user.is_authenticated:
                user = request.user
            ruta = ruta or (request.path[:255] if request.path else '')
            metodo = metodo or (request.method or '')
            forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
            if forwarded:
                ip = forwarded.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR')

        LogActividad.objects.create(
            usuario=user if getattr(user, 'is_authenticated', False) else None,
            tipo=tipo,
            accion=accion[:120],
            detalle=(detalle or '')[:2000],
            ruta=(ruta or '')[:255],
            metodo=(metodo or '')[:10],
            ip=ip,
        )
    except Exception:
        # Nunca tumbar la app por un fallo de logging
        pass
