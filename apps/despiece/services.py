import io
import os
import re
import logging
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
import pypdfium2 as pdfium
import pdfplumber

from apps.despiece.models import DespieceEquipo, DespieceItem, DespiecePagina
from apps.tienda.models import Producto

logger = logging.getLogger(__name__)

# SKU Makita típico: 265995-6, 511A48-8, 134862-5, DA00000156
_SKU_RE = re.compile(
    r'^(?:[A-Z]{1,3}\d{5,}|\d{3,}[A-Z0-9]{0,4}-\d{1,2}|[A-Z0-9]{4,12}-\d{1,4})$',
    re.I,
)
_POS_RE = re.compile(r'^(?:\d{1,3}(?:-\d{1,2})?|[A-Z]\d{0,2})$', re.I)
_POS_GLOBO_RE = re.compile(r'^\d{1,3}(?:-\d{1,2})?$')
_LINEA_PIEZA = re.compile(
    r'^(\d{1,3}(?:-\d{1,2})?|[A-Z]\d{0,2})\s+([A-Z0-9]{3,14}(?:-\d{1,4})?)\s+(.+?)(?:\s+(\d{1,3}))?\s*$',
    re.I,
)
_LINEA_ACCESORIO = re.compile(
    r'^([A-Z0-9]{3,14}(?:-\d{1,4})?)\s+(.+?)(?:\s+(\d{1,3}))?\s*$',
    re.I,
)
_PALABRAS_NO_SKU = {
    'CONTENIDO', 'PRECAUCION', 'PRECAUCIÓN', 'REPARO', 'DESMONTAJE',
    'MONTAJE', 'HERRAMIENTAS', 'APLICACION', 'APLICACIÓN', 'ESQUEMA',
}


def parse_page_spec(raw: str, n_pages: int) -> list[int]:
    """
    Convierte '1,2,5-7' en índices 0-based. Ignora fuera de rango.
    Vacío → lista vacía (el llamador decide el default).
    """
    if n_pages <= 0:
        return []
    text = (raw or '').strip()
    if not text:
        return []
    indices: list[int] = []
    seen = set()
    for chunk in text.replace(';', ',').split(','):
        piece = chunk.strip()
        if not piece:
            continue
        if '-' in piece and not piece.startswith('-'):
            a, _, b = piece.partition('-')
            try:
                start, end = int(a.strip()), int(b.strip())
            except ValueError:
                continue
            if start > end:
                start, end = end, start
            for num in range(start, end + 1):
                idx = num - 1
                if 0 <= idx < n_pages and idx not in seen:
                    seen.add(idx)
                    indices.append(idx)
        else:
            try:
                idx = int(piece) - 1
            except ValueError:
                continue
            if 0 <= idx < n_pages and idx not in seen:
                seen.add(idx)
                indices.append(idx)
    return indices


def clave_orden_posicion(pos: str) -> tuple:
    """1, 2, 126, 126-1, C10… luego letras sueltas y vacíos."""
    s = (pos or '').strip().upper()
    m = re.match(r'^(\d+)(?:-(\d+))?$', s)
    if m:
        return (0, int(m.group(1)), int(m.group(2) or 0))
    m = re.match(r'^C(\d{1,2})$', s)
    if m:
        return (0, 10_000, 100 + int(m.group(1)))
    if re.match(r'^[A-Z]$', s):
        return (1, ord(s[0]), 0)
    if not s:
        return (2, 0, 0)
    return (3, 0, 0)


def asignar_grupos_despiece(items: list) -> list:
    """
    Agrupa 013 + 013-1, y 015 + C10/C20 (internos del conjunto, no salen en el diagrama).
    Requiere ítems en orden de aparición (id / PDF).
    """
    ultimo = ''
    extra_vacios = 0
    for it in items:
        pos = (it.posicion or '').strip().upper()
        m = re.match(r'^(\d+)(?:-(\d+))?$', pos)
        if m:
            ultimo = m.group(1)
            extra_vacios = 0
            it.grupo = m.group(1)
            it.orden_extra = int(m.group(2) or 0)
            it.tipo_fila = 'sub' if m.group(2) else 'globo'
        elif re.match(r'^C\d{1,2}$', pos):
            it.grupo = ultimo or pos
            it.orden_extra = 100 + int(pos[1:])
            it.tipo_fila = 'interno'
        elif re.match(r'^[A-Z]$', pos):
            it.grupo = pos
            it.orden_extra = 0
            it.tipo_fila = 'acc'
        elif not pos:
            extra_vacios += 1
            if ultimo:
                it.grupo = ultimo
                it.orden_extra = 200 + extra_vacios
                it.tipo_fila = 'interno'
            else:
                it.grupo = 'ZZZ'
                it.orden_extra = extra_vacios
                it.tipo_fila = 'acc'
        else:
            it.grupo = pos
            it.orden_extra = 0
            it.tipo_fila = 'otro'
    last_numbered = -1
    for i, it in enumerate(items):
        if getattr(it, 'tipo_fila', '') in ('globo', 'sub'):
            last_numbered = i
    for it in items[last_numbered + 1:]:
        pos = (it.posicion or '').strip().upper()
        if getattr(it, 'tipo_fila', '') == 'interno' and not re.match(r'^C\d{1,2}$', pos):
            it.tipo_fila = 'acc'
            it.grupo = 'ZZZ'
    return items


def clave_orden_item_agrupado(it) -> tuple:
    grupo = (getattr(it, 'grupo', None) or it.posicion or '').strip().upper()
    extra = int(getattr(it, 'orden_extra', 0) or 0)
    if grupo.isdigit():
        return (0, int(grupo), extra)
    if grupo == 'ZZZ':
        return (2, 0, extra)
    return (1, 0, extra)


def es_sku_makita(codigo: str) -> bool:
    c = (codigo or '').strip().upper()
    if not c or c in _PALABRAS_NO_SKU or c.startswith('1R'):
        return False
    if '...' in c or '…' in c:
        return False
    return bool(_SKU_RE.match(c))


def normalizar_puntos_silueta(raw) -> list[dict]:
    """Lista de {x,y} en % (0–100). Máximo 400 puntos."""
    puntos = []
    if not isinstance(raw, list):
        return puntos
    for item in raw:
        if isinstance(item, dict):
            x, y = item.get('x'), item.get('y')
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            x, y = item[0], item[1]
        else:
            continue
        try:
            xf, yf = float(x), float(y)
        except (TypeError, ValueError):
            continue
        if 0 <= xf <= 100 and 0 <= yf <= 100:
            puntos.append({'x': round(xf, 3), 'y': round(yf, 3)})
        if len(puntos) >= 400:
            break
    return puntos


def centro_radio_silueta(puntos: list[dict]) -> tuple[float, float, float] | None:
    if len(puntos) < 3:
        return None
    cx = sum(p['x'] for p in puntos) / len(puntos)
    cy = sum(p['y'] for p in puntos) / len(puntos)
    radio = max(((p['x'] - cx) ** 2 + (p['y'] - cy) ** 2) ** 0.5 for p in puntos)
    return cx, cy, max(1.5, min(28.0, radio))


def _parse_linea_pieza(line: str) -> dict | None:
    line_str = (line or '').strip()
    if not line_str or line_str.count('.') >= 8 or '…' in line_str:
        return None
    if any(w in line_str for w in ('Artícu', 'No. de Partes', 'Por favor declare', 'Nº PARTE')):
        return None
    match_row = _LINEA_PIEZA.match(line_str)
    if match_row:
        pos, sku, desc, cant = match_row.groups()
        sku = sku.strip().upper()
        if es_sku_makita(sku) and _POS_RE.match(pos):
            desc = re.sub(r'\s+', ' ', desc).strip().upper()
            if desc and desc not in _PALABRAS_NO_SKU:
                return {
                    'posicion': pos.strip(),
                    'codigo_articulo': sku,
                    'descripcion': desc,
                    'cantidad': int(cant) if cant else 1,
                }
    match_acc = _LINEA_ACCESORIO.match(line_str)
    if not match_acc:
        return None
    sku, desc, cant = match_acc.groups()
    sku = sku.strip().upper()
    if not es_sku_makita(sku):
        return None
    desc = re.sub(r'\s+', ' ', desc).strip().upper()
    if not desc or desc in _PALABRAS_NO_SKU:
        return None
    return {
        'posicion': '',
        'codigo_articulo': sku,
        'descripcion': desc,
        'cantidad': int(cant) if cant else 1,
    }


def _filas_desde_tabla(table) -> list[dict]:
    rows = []
    if not table:
        return rows
    for raw in table:
        cells = [str(c or '').strip() for c in raw]
        if len(cells) < 2:
            continue
        pos = cells[0].split('\n')[0].strip()
        sku = cells[1].split('\n')[0].strip().upper()
        desc = ' '.join((cells[2] if len(cells) > 2 else '').split())
        if es_sku_makita(pos) and not _POS_RE.match(pos):
            desc = ' '.join((sku + ' ' + desc).split()) if sku and not es_sku_makita(sku) else desc or sku
            sku = pos.upper()
            pos = ''
        elif not es_sku_makita(sku) or not _POS_RE.match(pos):
            continue
        cant = 1
        if len(cells) >= 4:
            m = re.search(r'\d+', cells[-1].replace('\n', ' '))
            if m:
                cant = max(1, int(m.group(0)))
        rows.append({
            'posicion': pos,
            'codigo_articulo': sku,
            'descripcion': (desc or sku).upper(),
            'cantidad': cant,
        })
    return rows


def _parse_partes_desde_pdf(file_path: str, page_indices: list[int] | None = None):
    """Extrae modelo, nombre e ítems desde un PDF Makita (páginas 1-based vía índices 0-based)."""
    modelo = ''
    nombre_equipo = ''
    rows_parsed = []
    seen = set()

    with pdfplumber.open(file_path) as pdf:
        n_pages = len(pdf.pages)
        first_page_text = (pdf.pages[0].extract_text() or '') if n_pages else ''
        match_header = re.search(
            r'(?:Model\s*No\.?|No\.\s*de\s*Modelo|MODELO)\s*([A-Za-z0-9]+)\s*(.*)',
            first_page_text,
            re.IGNORECASE,
        )
        if match_header:
            modelo = match_header.group(1).strip().upper()
            nombre_equipo = match_header.group(2).strip().upper()[:180]

        if not modelo:
            stem = Path(file_path).stem.upper()
            stem = re.sub(r'-TE-SP$|-SP$|-TE$', '', stem)
            modelo = stem if stem else 'EQUIPO'

        if not nombre_equipo:
            nombre_equipo = f'EQUIPO MAKITA {modelo}'

        if page_indices is None:
            page_indices = list(range(n_pages))

        for page_idx in page_indices:
            if page_idx < 0 or page_idx >= n_pages:
                continue
            page = pdf.pages[page_idx]
            for table in (page.extract_tables() or []):
                for row in _filas_desde_tabla(table):
                    key = (row['posicion'], row['codigo_articulo'])
                    if key not in seen:
                        seen.add(key)
                        rows_parsed.append(row)
            for line in (page.extract_text() or '').split('\n'):
                row = _parse_linea_pieza(line)
                if not row:
                    continue
                key = (row['posicion'], row['codigo_articulo'])
                if key not in seen:
                    seen.add(key)
                    rows_parsed.append(row)

    return modelo, nombre_equipo, rows_parsed


def contar_paginas_pdf(file_path: str) -> int:
    pdf_doc = pdfium.PdfDocument(file_path)
    try:
        return len(pdf_doc)
    finally:
        pdf_doc.close()


def parece_manual_reparacion(file_path: str) -> bool:
    """True si el PDF parece TE-SP / manual de reparación (sin lista MSI de SKU)."""
    stem = Path(file_path).stem.upper()
    if '-TE-SP' in stem or stem.endswith('-TE') or 'REPAIR' in stem:
        return True
    try:
        with pdfplumber.open(file_path) as pdf:
            chunks = []
            for page in pdf.pages[:3]:
                chunks.append(page.extract_text() or '')
            text = '\n'.join(chunks).upper()
    except Exception:
        return False
    return any(
        token in text
        for token in (
            'MANUAL DE REPAR',
            'REPAIR MANUAL',
            'FOR ASC',
            'OFFICIAL USE',
            '5 REPARO',
        )
    )


def _render_paginas_pdf(file_path: str, page_indices: list[int] | None = None, max_diagram_pages: int = 3):
    """Renderiza páginas concretas del PDF como PNG (diagramas)."""
    pdf_doc = pdfium.PdfDocument(file_path)
    try:
        n = len(pdf_doc)
        if page_indices is None:
            page_indices = list(range(min(n, max_diagram_pages)))
        pages = []
        for i in page_indices[:12]:
            if i < 0 or i >= n:
                continue
            pil_image = pdf_doc[i].render(scale=2.0).to_pil()
            buf = io.BytesIO()
            pil_image.save(buf, format='PNG')
            pages.append(buf.getvalue())
        return pages
    finally:
        pdf_doc.close()


def _guardar_paginas(despiece: DespieceEquipo, png_bytes_list, reemplazar=True):
    if reemplazar:
        for p in despiece.paginas.all():
            if p.imagen:
                p.imagen.delete(save=False)
            p.delete()

    for i, raw in enumerate(png_bytes_list, start=1):
        pagina = DespiecePagina(despiece=despiece, numero=i)
        pagina.imagen.save(
            f'{despiece.modelo.lower()}_p{i}.png',
            ContentFile(raw),
            save=True,
        )

    if png_bytes_list:
        despiece.imagen_diagrama.save(
            f'{despiece.modelo.lower()}_diagrama.png',
            ContentFile(png_bytes_list[0]),
            save=False,
        )
        despiece.save(update_fields=['imagen_diagrama'])


def _guardar_items(despiece: DespieceEquipo, rows_parsed):
    despiece.items.all().delete()
    skus = [r['codigo_articulo'] for r in rows_parsed]
    productos_map = {
        p.codigo_articulo: p
        for p in Producto.objects.filter(codigo_articulo__in=skus)
    }
    items_to_create = [
        DespieceItem(
            despiece=despiece,
            posicion=row['posicion'],
            codigo_articulo=row['codigo_articulo'],
            descripcion=row['descripcion'],
            cantidad=row['cantidad'],
            producto=productos_map.get(row['codigo_articulo']),
        )
        for row in rows_parsed
    ]
    DespieceItem.objects.bulk_create(items_to_create)
    despiece.total_partes = len(items_to_create)
    despiece.save(update_fields=['total_partes'])


def procesar_pdf_despiece(file_path: str) -> DespieceEquipo:
    """
    Lee un PDF de despiece Makita desde disco (carpeta resources/).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f'El archivo PDF {file_path} no existe.')

    modelo, nombre_equipo, rows_parsed = _parse_partes_desde_pdf(file_path)
    png_pages = _render_paginas_pdf(file_path, max_diagram_pages=2)

    despiece, _ = DespieceEquipo.objects.get_or_create(
        modelo=modelo,
        defaults={
            'nombre_equipo': nombre_equipo,
            'archivo_pdf': os.path.basename(file_path),
        },
    )
    despiece.nombre_equipo = nombre_equipo
    despiece.archivo_pdf = os.path.basename(file_path)
    despiece.save()

    _guardar_paginas(despiece, png_pages, reemplazar=True)
    _guardar_items(despiece, rows_parsed)
    return despiece


def crear_despiece_desde_upload(
    pdf_file=None,
    imagenes=None,
    modelo_override='',
    nombre_override='',
    max_diagram_pages=3,
    paginas_diagrama='',
    paginas_piezas='',
    despiece_existente=None,
) -> DespieceEquipo:
    """
    Crea/actualiza un despiece desde archivos subidos por el POS.
    paginas_diagrama / paginas_piezas: '1,2' o '7-9' (1-based).
    Si no hay PDF nuevo, reprocesa el ya guardado en despiece_existente.
    """
    imagenes = [f for f in (imagenes or []) if f]
    tmp_path = None
    created_tmp = False
    suffix = '.pdf'

    if pdf_file:
        suffix = Path(getattr(pdf_file, 'name', 'despiece.pdf')).suffix or '.pdf'
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in pdf_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        created_tmp = True
    elif despiece_existente and despiece_existente.pdf:
        tmp_path = despiece_existente.pdf.path
        suffix = Path(tmp_path).suffix or '.pdf'
    else:
        raise ValueError('Falta el PDF de despiece.')

    try:
        n_pages = contar_paginas_pdf(tmp_path)
        idx_piezas = parse_page_spec(paginas_piezas, n_pages)
        idx_diag = parse_page_spec(paginas_diagrama, n_pages)
        if not idx_diag:
            idx_diag = list(range(min(n_pages, max_diagram_pages)))

        modelo, nombre_equipo, rows_parsed = _parse_partes_desde_pdf(
            tmp_path,
            page_indices=idx_piezas or None,
        )
        if modelo_override.strip():
            modelo = modelo_override.strip().upper()
        elif despiece_existente and despiece_existente.modelo:
            modelo = despiece_existente.modelo
        if nombre_override.strip():
            nombre_equipo = nombre_override.strip()
        elif despiece_existente and despiece_existente.nombre_equipo and not nombre_equipo:
            nombre_equipo = despiece_existente.nombre_equipo

        png_from_pdf = _render_paginas_pdf(tmp_path, page_indices=idx_diag)

        despiece, _ = DespieceEquipo.objects.get_or_create(
            modelo=modelo,
            defaults={'nombre_equipo': nombre_equipo},
        )
        despiece.nombre_equipo = nombre_equipo
        if pdf_file:
            despiece.archivo_pdf = getattr(pdf_file, 'name', '') or f'{modelo}.pdf'
            pdf_file.seek(0)
            despiece.pdf.save(
                f'{modelo.lower()}{suffix.lower()}',
                pdf_file,
                save=False,
            )
        elif not despiece.archivo_pdf:
            despiece.archivo_pdf = f'{modelo}.pdf'
        despiece.save()

        if imagenes:
            png_bytes_list = []
            for img in imagenes:
                png_bytes_list.append(img.read())
                try:
                    img.seek(0)
                except Exception:
                    pass
            _guardar_paginas(despiece, png_bytes_list, reemplazar=True)
        else:
            _guardar_paginas(despiece, png_from_pdf, reemplazar=True)

        _guardar_items(despiece, rows_parsed)
        despiece._n_paginas_pdf = n_pages
        despiece._es_manual_reparacion = parece_manual_reparacion(tmp_path)
        return despiece
    finally:
        if created_tmp and tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def sincronizar_despiece_productos(despiece: DespieceEquipo):
    """Vuelve a asociar DespieceItem con los productos en la base de datos."""
    from django.db.models.functions import Upper
    items = list(despiece.items.all())
    if not items:
        return
    skus = [(it.codigo_articulo or '').strip().upper() for it in items]
    productos_map = {
        (p.codigo_articulo or '').strip().upper(): p
        for p in Producto.objects.annotate(sku_up=Upper('codigo_articulo')).filter(sku_up__in=skus)
    }
    to_update = []
    for item in items:
        prod = productos_map.get((item.codigo_articulo or '').strip().upper())
        if prod and item.producto_id != prod.id:
            item.producto = prod
            to_update.append(item)
    if to_update:
        DespieceItem.objects.bulk_update(to_update, ['producto'])
