import os
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.conf import settings
from django.core.paginator import Paginator

from apps.sistema.internal_access import is_staff_interno, puede_usar_pos, redirect_pos_login, ocultar_sistema_interno
from apps.despiece.models import DespieceEquipo, DespieceItem
from apps.despiece.services import procesar_pdf_despiece, sincronizar_despiece_productos


def staff_pos_required(view_func):
    """Acceso exclusivo a staff interno (POS / vendedor / admin)."""
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_pos_login(request)
        if not puede_usar_pos(request.user):
            return ocultar_sistema_interno(request)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@staff_pos_required
def despiece_lista(request):
    """Lista de despieces de equipos Makita procesados."""
    q = (request.GET.get('q') or '').strip()
    qs = DespieceEquipo.objects.all().order_by('modelo')

    if q:
        # Buscar por modelo de equipo o por código de repuesto contenido
        qs = qs.filter(
            models.Q(modelo__icontains=q)
            | models.Q(nombre_equipo__icontains=q)
            | models.Q(items__codigo_articulo__icontains=q)
            | models.Q(items__descripcion__icontains=q)
        ).distinct()

    page = Paginator(qs, 24).get_page(request.GET.get('page'))

    return render(request, 'pos/despiece_lista.html', {
        'titulo': 'Despieces y Diagramas Makita',
        'subtitulo': 'Explora planos explosionados de herramientas y consulta repuestos con precio y stock',
        'q': q,
        'page_obj': page,
        'modo': 'despieces',
        'search_placeholder': 'Modelo (ej. GA4590), código de parte o descripción…',
    })


@staff_pos_required
def despiece_visor(request, modelo):
    """Visor interactivo del despiece de un equipo Makita (plano a la izquierda, partes a la derecha)."""
    despiece = get_object_or_404(DespieceEquipo, modelo__iexact=modelo)

    # Sincronizar catálogo por si hubo nuevos precios/productos
    sincronizar_despiece_productos(despiece)

    items = despiece.items.select_related('producto').all().order_by('id')

    q_item = (request.GET.get('q') or '').strip()
    if q_item:
        items = items.filter(
            models.Q(posicion__icontains=q_item)
            | models.Q(codigo_articulo__icontains=q_item)
            | models.Q(descripcion__icontains=q_item)
        )

    from apps.sistema.stock import stock_para_venta
    from apps.pos.models import CajaSesion

    sesion = CajaSesion.objects.filter(cajero=request.user, estado=CajaSesion.ESTADO_ABIERTA).select_related('sede').first()
    sede = sesion.sede if sesion else None

    parts_data = []
    for item in items:
        prod = item.producto
        stock_disp = stock_para_venta(prod, sede) if prod else 0
        parts_data.append({
            'id': item.id,
            'posicion': item.posicion,
            'codigo_articulo': item.codigo_articulo,
            'descripcion': item.descripcion,
            'cantidad': item.cantidad,
            'producto_id': prod.id if prod else None,
            'precio_con_igv': str(prod.precio_lista_con_igv) if prod else '—',
            'precio_venta': str(prod.precio_venta) if prod else '0.00',
            'stock': prod.stock if prod else 0,
            'stock_web': prod.stock_web if prod else 0,
            'stock_disponible': stock_disp,
            'tipo': prod.tipo if prod else 'repuesto',
            'lima_label': prod.disponibilidad_lima_label if prod else '',
            'lima_css': prod.disponibilidad_lima_css if prod else '',
        })

    import json

    return render(request, 'pos/despiece_visor.html', {
        'despiece': despiece,
        'parts_data_json': json.dumps(parts_data),
        'q_item': q_item,
        'total_partes': len(parts_data),
    })


@staff_pos_required
def despiece_escanear_directorio(request):
    """Escanea el directorio resources/despieces/ en busca de nuevos PDFs e ingesta."""
    folder = os.path.join(settings.BASE_DIR, 'resources', 'despieces')
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

    procesados = 0
    errores = []

    for filename in os.listdir(folder):
        if filename.lower().endswith('.pdf'):
            full_path = os.path.join(folder, filename)
            try:
                procesar_pdf_despiece(full_path)
                procesados += 1
            except Exception as e:
                errores.append(f"{filename}: {str(e)}")

    if procesados > 0:
        messages.success(request, f"Se procesaron {procesados} despiece(s) correctamente.")
    else:
        messages.info(request, "No se encontraron nuevos PDFs para procesar en resources/despieces/.")

    if errores:
        messages.warning(request, f"Errores: {'; '.join(errores)}")

    return redirect('despiece:despiece_lista')
