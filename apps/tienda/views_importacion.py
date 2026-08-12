from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.tienda.importers.makita_excel import importar_catalogo_makita
from apps.tienda.models import ImportacionCatalogo


def _staff_ok(request):
    return request.user.is_authenticated and (
        request.user.is_superuser
        or getattr(request.user, 'rol', None) in ('admin', 'vendedor')
        or request.user.is_staff
    )


@staff_member_required
def importar_catalogo_view(request):
    """Redirige al hub interno con el diseño POS."""
    if not _staff_ok(request):
        messages.error(request, 'No tiene permisos para importar catálogo.')
        return redirect('admin:index')
    return redirect('pos:hub_importar')


@staff_member_required
@require_http_methods(['POST'])
def importar_catalogo_upload(request):
    if not _staff_ok(request):
        messages.error(request, 'No tiene permisos para importar catálogo.')
        return redirect('admin:index')

    archivo = request.FILES.get('archivo')
    tipo = request.POST.get('tipo_archivo') or ImportacionCatalogo.TIPO_AUTO

    if not archivo:
        messages.error(request, 'Selecciona un archivo Excel (.xlsx).')
        return redirect('pos:hub_importar')

    if not archivo.name.lower().endswith(('.xlsx', '.xlsm')):
        messages.error(request, 'El archivo debe ser .xlsx (formato Makita).')
        return redirect('pos:hub_importar')

    if ImportacionCatalogo.objects.filter(estado__in=['pendiente', 'procesando']).exists():
        messages.error(request, 'Ya hay una importación en curso.')
        return redirect('pos:hub_importar')

    try:
        imp = importar_catalogo_makita(
            file_obj=archivo,
            archivo_nombre=archivo.name,
            tipo_archivo=tipo,
            usuario=request.user,
            en_background=True,
        )
        messages.success(
            request,
            f'Importación #{imp.id} iniciada en segundo plano. Puedes seguir trabajando.',
        )
    except Exception as exc:
        messages.error(request, f'Error al importar: {exc}')

    return redirect('pos:hub_importar')
