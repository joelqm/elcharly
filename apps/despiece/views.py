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
from apps.despiece.models import DespieceEquipo, DespieceHotspot, DespiecePagina, DespieceItem
from apps.despiece.services import (
    procesar_pdf_despiece,
    sincronizar_despiece_productos,
    crear_despiece_desde_upload,
    contar_paginas_pdf,
    normalizar_puntos_silueta,
    centro_radio_silueta,
    asignar_grupos_despiece,
    clave_orden_item_agrupado,
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

    items = asignar_grupos_despiece(list(
        despiece.items.select_related('producto').all().order_by('id')
    ))
    items.sort(key=clave_orden_item_agrupado)

    from apps.sistema.stock import stock_para_venta
    from apps.pos.models import CajaSesion

    sesion = CajaSesion.objects.filter(
        cajero=request.user, estado=CajaSesion.ESTADO_ABIERTA,
    ).select_related('sede').first()
    sede = sesion.sede if sesion else None

    parts_data = []
    for item in items:
        prod = item.producto
        stock_tienda = int(prod.stock or 0) if prod else 0
        stock_web = int(prod.stock_web or 0) if prod else 0
        stock_disp = stock_para_venta(prod, sede) if prod else 0
        if stock_disp <= 0 and (stock_tienda > 0 or stock_web > 0):
            stock_disp = stock_tienda + stock_web
        tipo_fila = getattr(item, 'tipo_fila', 'globo')
        nombre_sistema = ((prod.nombre if prod else '') or item.descripcion or '').strip()
        nombre_guia = (item.descripcion or '').strip()
        if nombre_guia.upper() == nombre_sistema.upper():
            nombre_guia = ''
        parts_data.append({
            'id': item.id,
            'posicion': item.posicion,
            'grupo': getattr(item, 'grupo', item.posicion or ''),
            'codigo_articulo': item.codigo_articulo,
            'descripcion': nombre_sistema,
            'nombre_guia': nombre_guia,
            'cantidad': item.cantidad,
            'producto_id': prod.id if prod else None,
            'precio_con_igv': str(prod.precio_lista_con_igv) if prod else '—',
            'precio_venta': str(prod.precio_venta) if prod else '0.00',
            'stock': stock_tienda,
            'stock_web': stock_web,
            'stock_disponible': int(stock_disp),
            'tipo': prod.tipo if prod else 'repuesto',
            'lima_label': prod.disponibilidad_lima_label if prod else '',
            'lima_css': prod.disponibilidad_lima_css if prod else '',
            'es_subpieza': tipo_fila == 'sub',
            'es_interno': tipo_fila == 'interno',
            'es_accesorio': tipo_fila == 'acc',
        })

    hotspots = [_hotspot_payload(h) for h in despiece.hotspots.all()]

    return render(request, 'pos/despiece_visor.html', {
        'despiece': despiece,
        'parts_data_json': json.dumps(parts_data),
        'hotspots_json': json.dumps(hotspots),
        'paginas_json': json.dumps(_paginas_payload(despiece)),
        'total_partes': len(parts_data),
        'csrf_token': request.META.get('CSRF_COOKIE', ''),
    })


def _hotspot_payload(hs):
    return {
        'id': hs.id,
        'pagina': hs.pagina,
        'posicion': hs.posicion,
        'cx': hs.cx,
        'cy': hs.cy,
        'r': hs.r,
        'puntos': hs.puntos or [],
    }


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
        puntos = normalizar_puntos_silueta(data.get('puntos') or [])
        centro = centro_radio_silueta(puntos)
        if centro:
            cx, cy, r = centro
        else:
            cx = float(data.get('cx'))
            cy = float(data.get('cy'))
            r = float(data.get('r') or 2.2)
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Coordenadas inválidas.'}, status=400)

    hs, _ = DespieceHotspot.objects.update_or_create(
        despiece=despiece,
        pagina=pagina,
        posicion=posicion,
        defaults={
            'cx': cx,
            'cy': cy,
            'r': max(1.5, min(28.0, r)),
            'puntos': puntos,
        },
    )
    return JsonResponse({
        'ok': True,
        'hotspot': _hotspot_payload(hs),
    })


@staff_pos_required
@require_POST
def despiece_eliminar_hotspot(request, modelo):
    """Quita una marca del diagrama si se eligió mal."""
    despiece = get_object_or_404(DespieceEquipo, modelo__iexact=modelo)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    posicion = str(data.get('posicion') or '').strip()
    try:
        pagina = int(data.get('pagina') or 1)
    except (TypeError, ValueError):
        pagina = 1
    if not posicion:
        return JsonResponse({'ok': False, 'error': 'Indica la posición a quitar.'}, status=400)

    deleted, _ = DespieceHotspot.objects.filter(
        despiece=despiece,
        pagina=pagina,
        posicion=posicion,
    ).delete()
    if not deleted:
        deleted, _ = DespieceHotspot.objects.filter(
            despiece=despiece,
            posicion=posicion,
        ).delete()
    return JsonResponse({'ok': True, 'deleted': deleted})


@staff_pos_required
def despiece_donde_se_usa(request, modelo):
    """Equipos/despieces donde aparece el mismo SKU (repuesto compartido)."""
    sku = (request.GET.get('sku') or '').strip().upper()
    if not sku:
        return JsonResponse({'ok': False, 'error': 'Falta el código.'}, status=400)
    qs = (
        DespieceItem.objects.filter(codigo_articulo__iexact=sku)
        .select_related('despiece')
        .order_by('despiece__modelo', 'id')
    )
    usos = []
    seen = set()
    for it in qs:
        key = (it.despiece.modelo.upper(), (it.posicion or '').upper())
        if key in seen:
            continue
        seen.add(key)
        usos.append({
            'modelo': it.despiece.modelo,
            'nombre_equipo': it.despiece.nombre_equipo,
            'posicion': it.posicion or 'ACC',
            'es_actual': it.despiece.modelo.upper() == (modelo or '').upper(),
        })
    return JsonResponse({'ok': True, 'sku': sku, 'usos': usos})


@staff_pos_required
def despiece_subir(request):
    """Formulario para crear/actualizar un despiece subiendo PDF (+ imágenes opcionales)."""
    despiece_prev = None
    modelo_q = (request.GET.get('modelo') or '').strip()
    if modelo_q:
        despiece_prev = DespieceEquipo.objects.filter(modelo__iexact=modelo_q).first()

    if request.method == 'POST':
        pdf = request.FILES.get('pdf')
        modelo_override = (request.POST.get('modelo') or '').strip()
        nombre_override = (request.POST.get('nombre_equipo') or '').strip()
        paginas_diagrama = (request.POST.get('paginas_diagrama') or '').strip()
        paginas_piezas = (request.POST.get('paginas_piezas') or '').strip()

        if modelo_override and not despiece_prev:
            despiece_prev = DespieceEquipo.objects.filter(modelo__iexact=modelo_override).first()

        if not pdf and not (despiece_prev and despiece_prev.pdf):
            messages.error(request, 'Selecciona el PDF de despiece Makita.')
            return redirect(request.path)

        if pdf:
            name = (pdf.name or '').lower()
            if not name.endswith('.pdf'):
                messages.error(request, 'El archivo principal debe ser un PDF.')
                return redirect(request.path)

        imagenes = request.FILES.getlist('imagenes')

        try:
            despiece = crear_despiece_desde_upload(
                pdf_file=pdf,
                imagenes=imagenes,
                modelo_override=modelo_override,
                nombre_override=nombre_override,
                paginas_diagrama=paginas_diagrama,
                paginas_piezas=paginas_piezas,
                despiece_existente=despiece_prev,
            )
        except Exception as exc:
            logger = __import__('logging').getLogger(__name__)
            logger.exception('Error al subir despiece')
            messages.error(request, f'No se pudo procesar el despiece: {exc}')
            qs = f'?modelo={modelo_override}' if modelo_override else ''
            return redirect(f'{request.path}{qs}' if qs else request.path)

        extra = ''
        if imagenes:
            extra = f' · {len(imagenes)} imagen(es) de diagrama'
        n_pdf = getattr(despiece, '_n_paginas_pdf', None)
        if n_pdf:
            extra += f' · PDF de {n_pdf} páginas'
        if despiece.total_partes:
            messages.success(
                request,
                f'Despiece {despiece.modelo} listo: {despiece.total_partes} piezas{extra}. '
                'Puedes marcar números sobre el diagrama.',
            )
        else:
            aviso = (
                f'Se actualizó {despiece.modelo}{extra}, pero no hay lista de piezas (SKU). '
            )
            if getattr(despiece, '_es_manual_reparacion', False):
                aviso += (
                    'Este archivo parece un manual de reparación (TE-SP), no el catálogo Web-MSI. '
                    'Indica las páginas del diagrama explosionado y, si el PDF las trae, las de la lista; '
                    'o sube el PDF de partes / capturas MSI.'
                )
            else:
                aviso += (
                    'Indica en el formulario las páginas de la lista de piezas (ej. 20-28) '
                    'o sube el PDF Web-MSI de repuestos.'
                )
            messages.warning(request, aviso)
        return redirect('despiece:despiece_visor', modelo=despiece.modelo)

    n_paginas_pdf = 0
    if despiece_prev and despiece_prev.pdf:
        try:
            n_paginas_pdf = contar_paginas_pdf(despiece_prev.pdf.path)
        except Exception:
            n_paginas_pdf = 0

    return render(request, 'pos/despiece_subir.html', {
        'despiece_prev': despiece_prev,
        'n_paginas_pdf': n_paginas_pdf,
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
