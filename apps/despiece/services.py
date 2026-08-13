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


def _parse_partes_desde_pdf(file_path: str):
    """Extrae modelo, nombre e ítems desde un PDF Makita."""
    modelo = ''
    nombre_equipo = ''
    rows_parsed = []

    with pdfplumber.open(file_path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ''
        match_header = re.search(
            r'Model\s*No\.?\s*([A-Za-z0-9]+)\s*(.*)',
            first_page_text,
            re.IGNORECASE,
        )
        if match_header:
            modelo = match_header.group(1).strip().upper()
            nombre_equipo = match_header.group(2).strip().upper()

        if not modelo:
            base_name = Path(file_path).stem.upper()
            modelo = base_name if base_name else 'EQUIPO'

        if not nombre_equipo:
            nombre_equipo = f'EQUIPO MAKITA {modelo}'

        for page_idx in range(1, len(pdf.pages)):
            text_lines = (pdf.pages[page_idx].extract_text() or '').split('\n')
            for line in text_lines:
                line_str = line.strip()
                if (
                    not line_str
                    or 'Artícu' in line_str
                    or 'No. de Partes' in line_str
                    or 'Por favor declare' in line_str
                ):
                    continue
                match_row = re.match(
                    r'^([A-Za-z0-9\-]+)\s+([A-Za-z0-9\-]{5,15})\s+(.+?)\s+([0-9]+)(?:\s+.*)?$',
                    line_str,
                )
                if match_row:
                    rows_parsed.append({
                        'posicion': match_row.group(1).strip(),
                        'codigo_articulo': match_row.group(2).strip().upper(),
                        'descripcion': match_row.group(3).strip().upper(),
                        'cantidad': int(match_row.group(4)),
                    })

    return modelo, nombre_equipo, rows_parsed


def _render_paginas_pdf(file_path: str, max_diagram_pages: int = 3):
    """
    Renderiza las primeras páginas del PDF como PNG (diagramas).
    Las páginas de tabla de partes suelen ser texto; limitamos a las primeras.
    """
    pdf_doc = pdfium.PdfDocument(file_path)
    pages = []
    n = min(len(pdf_doc), max_diagram_pages)
    for i in range(n):
        pil_image = pdf_doc[i].render(scale=2.0).to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format='PNG')
        pages.append(buf.getvalue())
    return pages


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
    pdf_file,
    imagenes=None,
    modelo_override='',
    nombre_override='',
    max_diagram_pages=3,
) -> DespieceEquipo:
    """
    Crea/actualiza un despiece desde archivos subidos por el POS.
    - PDF: lista de partes + render de páginas de diagrama
    - Imágenes opcionales: reemplazan las páginas del diagrama (útil con capturas MSI)
    """
    imagenes = [f for f in (imagenes or []) if f]

    suffix = Path(getattr(pdf_file, 'name', 'despiece.pdf')).suffix or '.pdf'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        for chunk in pdf_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        modelo, nombre_equipo, rows_parsed = _parse_partes_desde_pdf(tmp_path)
        if modelo_override.strip():
            modelo = modelo_override.strip().upper()
        if nombre_override.strip():
            nombre_equipo = nombre_override.strip()

        png_from_pdf = _render_paginas_pdf(tmp_path, max_diagram_pages=max_diagram_pages)

        despiece, _ = DespieceEquipo.objects.get_or_create(
            modelo=modelo,
            defaults={'nombre_equipo': nombre_equipo},
        )
        despiece.nombre_equipo = nombre_equipo
        despiece.archivo_pdf = getattr(pdf_file, 'name', '') or f'{modelo}.pdf'
        pdf_file.seek(0)
        despiece.pdf.save(
            f'{modelo.lower()}{suffix.lower()}',
            pdf_file,
            save=False,
        )
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
        return despiece
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def sincronizar_despiece_productos(despiece: DespieceEquipo):
    """Vuelve a asociar DespieceItem con los productos en la base de datos."""
    skus = despiece.items.values_list('codigo_articulo', flat=True)
    productos_map = {
        p.codigo_articulo: p for p in Producto.objects.filter(codigo_articulo__in=skus)
    }
    for item in despiece.items.all():
        if item.codigo_articulo in productos_map:
            item.producto = productos_map[item.codigo_articulo]
            item.save(update_fields=['producto'])
