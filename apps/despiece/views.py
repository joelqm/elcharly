import json
import os

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.conf import settings
from django.core.paginator import Paginator
from django.db import models
from django.views.decorators.http import require_POST

from apps.sistema.internal_access import puede_usar_pos, redirect_pos_login, ocultar_sistema_interno
from apps.despiece.models import DespieceEquipo, DespieceHotspot, DespiecePagina
from apps.despiece.services import (
    procesar_pdf_despiece,
    sincronizar_despiece_productos,
    crear_despiece_desde_upload,
)


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


def _paginas_payload(despiece):
    pags = list(despiece.paginas.order_by('numero'))
    if pags:
        return [{'numero': p.numero, 'url': p.imagen.url} for p in pags if p.imagen]
    if despiece.imagen_diagrama:
        return [{'numero': 1, 'url': despiece.imagen_diagrama.url}]
    return []


@staff_pos_required
def despiece_visor(request, modelo):
    """Visor interactivo del despiece (plano + lista + hotspots)."""
    despiece = get_object_or_404(DespieceEquipo, modelo__iexact=modelo)

    # Solo re-vincular si hay ítems (evita trabajo vacío en modelos solo con imagen)
    if despiece.items.exists():
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

    sesion = CajaSesion.objects.filter(
        cajero=request.user, estado=CajaSesion.ESTADO_ABIERTA,
    ).select_related('sede').first()
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

    hotspots = [
        {
            'id': h.id,
            'pagina': h.pagina,
            'posicion': h.posicion,
            'cx': h.cx,
            'cy': h.cy,
            'r': h.r,
        }
        for h in despiece.hotspots.all()
    ]

    return render(request, 'pos/despiece_visor.html', {
        'despiece': despiece,
        'parts_data_json': json.dumps(parts_data),
        'hotspots_json': json.dumps(hotspots),
        'paginas_json': json.dumps(_paginas_payload(despiece)),
        'q_item': q_item,
        'total_partes': len(parts_data),
        'csrf_token': request.META.get('CSRF_COOKIE', ''),
    })


@staff_pos_required
@require_POST
def despiece_guardar_hotspot(request, modelo):
    """Guarda o actualiza un hotspot (coordenadas en % 0–100)."""
    despiece = get_object_or_404(DespieceEquipo, modelo__iexact=modelo)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    posicion = str(data.get('posicion') or '').strip()
    if not posicion:
        return JsonResponse({'ok': False, 'error': 'Indica la posición (nº del diagrama).'}, status=400)

    try:
        pagina = int(data.get('pagina') or 1)
        cx = float(data.get('cx'))
        cy = float(data.get('cy'))
        r = float(data.get('r') or 2.2)
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Coordenadas inválidas.'}, status=400)

    hs, _ = DespieceHotspot.objects.update_or_create(
        despiece=despiece,
        pagina=pagina,
        posicion=posicion,
        defaults={'cx': cx, 'cy': cy, 'r': max(1.0, min(8.0, r))},
    )
    return JsonResponse({
        'ok': True,
        'hotspot': {
            'id': hs.id,
            'pagina': hs.pagina,
            'posicion': hs.posicion,
            'cx': hs.cx,
            'cy': hs.cy,
            'r': hs.r,
        },
    })


@staff_pos_required
def despiece_subir(request):
    """Formulario para crear/actualizar un despiece subiendo PDF (+ imágenes opcionales)."""
    despiece_prev = None
    modelo_q = (request.GET.get('modelo') or '').strip()
    if modelo_q:
        despiece_prev = DespieceEquipo.objects.filter(modelo__iexact=modelo_q).first()

    if request.method == 'POST':
        pdf = request.FILES.get('pdf')
        if not pdf:
            messages.error(request, 'Selecciona el PDF de despiece Makita.')
            return redirect('despiece:despiece_subir')

        name = (pdf.name or '').lower()
        if not name.endswith('.pdf'):
            messages.error(request, 'El archivo principal debe ser un PDF.')
            return redirect('despiece:despiece_subir')

        imagenes = request.FILES.getlist('imagenes')
        modelo_override = (request.POST.get('modelo') or '').strip()
        nombre_override = (request.POST.get('nombre_equipo') or '').strip()
        try:
            max_pages = int(request.POST.get('max_paginas') or 3)
        except ValueError:
            max_pages = 3
        max_pages = max(1, min(6, max_pages))

        try:
            despiece = crear_despiece_desde_upload(
                pdf_file=pdf,
                imagenes=imagenes,
                modelo_override=modelo_override,
                nombre_override=nombre_override,
                max_diagram_pages=max_pages,
            )
        except Exception as exc:
            logger = __import__('logging').getLogger(__name__)
            logger.exception('Error al subir despiece')
            messages.error(request, f'No se pudo procesar el despiece: {exc}')
            return redirect('despiece:despiece_subir')

        extra = ''
        if imagenes:
            extra = f' · {len(imagenes)} imagen(es) de diagrama'
        messages.success(
            request,
            f'Despiece {despiece.modelo} listo: {despiece.total_partes} partes{extra}. '
            'Puedes mapear hotspots en el visor.',
        )
        return redirect('despiece:despiece_visor', modelo=despiece.modelo)

    return render(request, 'pos/despiece_subir.html', {
        'despiece_prev': despiece_prev,
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
            except Exception as exc:
                errores.append(f'{filename}: {exc}')

    if procesados:
        messages.success(request, f'Se procesaron {procesados} PDF(s) de despiece.')
    if errores:
        messages.error(request, 'Errores: ' + '; '.join(errores[:5]))
    if not procesados and not errores:
        messages.info(request, 'No hay PDFs nuevos en resources/despieces/.')

    return redirect('despiece:despiece_lista')
