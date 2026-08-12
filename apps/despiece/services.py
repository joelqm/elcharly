import os
import re
import logging
from django.conf import settings
from django.core.files.base import ContentFile
import pypdfium2 as pdfium
import pdfplumber

from apps.despiece.models import DespieceEquipo, DespieceItem
from apps.tienda.models import Producto

logger = logging.getLogger(__name__)


def procesar_pdf_despiece(file_path: str) -> DespieceEquipo:
    """
    Lee un PDF de despiece Makita (ej. GA4590.pdf), extrae la imagen del diagrama
    de la pág. 1 y la lista de partes de las págs. 2+, asociando cada repuesto a su SKU en catálogo.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"El archivo PDF {file_path} no existe.")

    # 1. Renderizar la página 1 del PDF como imagen PNG de alta calidad
    pdf_doc = pdfium.PdfDocument(file_path)
    page_1 = pdf_doc[0]
    pil_image = page_1.render(scale=2.2).to_pil()
    
    # 2. Extraer modelo y nombre del equipo usando pdfplumber
    modelo = ''
    nombre_equipo = ''
    rows_parsed = []

    with pdfplumber.open(file_path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ''
        match_header = re.search(r'Model\s*No\.?\s*([A-Za-z0-9]+)\s*(.*)', first_page_text, re.IGNORECASE)
        if match_header:
            modelo = match_header.group(1).strip().upper()
            nombre_equipo = match_header.group(2).strip().upper()

        if not modelo:
            # Fallback del nombre de archivo (ej. GA4590.pdf)
            base_name = os.path.basename(file_path).split('.')[0].upper()
            modelo = base_name if base_name else 'EQUIPO'

        if not nombre_equipo:
            nombre_equipo = f"EQUIPO MAKITA {modelo}"

        # Recorrer páginas 2 en adelante para extraer la tabla de partes
        for page_idx in range(1, len(pdf.pages)):
            text_lines = (pdf.pages[page_idx].extract_text() or '').split('\n')
            for line in text_lines:
                line_str = line.strip()
                if not line_str or 'Artícu' in line_str or 'No. de Partes' in line_str or 'Por favor declare' in line_str:
                    continue
                
                # Regex para capturar líneas como:
                # 016 511A48-8 Montaje de la armadura 220V 1
                # 068-1 262211-7 Anillo de goma 37 < 1 *
                match_row = re.match(
                    r'^([A-Za-z0-9\-]+)\s+([A-Za-z0-9\-]{5,15})\s+(.+?)\s+([0-9]+)(?:\s+.*)?$',
                    line_str
                )
                if match_row:
                    pos = match_row.group(1).strip()
                    sku = match_row.group(2).strip().upper()
                    desc = match_row.group(3).strip().upper()
                    cant = int(match_row.group(4))
                    rows_parsed.append({
                        'posicion': pos,
                        'codigo_articulo': sku,
                        'descripcion': desc,
                        'cantidad': cant,
                    })

    # 3. Guardar o actualizar DespieceEquipo
    despiece, _ = DespieceEquipo.objects.get_or_create(
        modelo=modelo,
        defaults={
            'nombre_equipo': nombre_equipo,
            'archivo_pdf': os.path.basename(file_path),
        }
    )
    despiece.nombre_equipo = nombre_equipo
    despiece.archivo_pdf = os.path.basename(file_path)

    # Guardar imagen renderizada en ImageField
    import io
    img_byte_arr = io.BytesIO()
    pil_image.save(img_byte_arr, format='PNG')
    filename = f"{modelo.lower()}_diagrama.png"
    despiece.imagen_diagrama.save(filename, ContentFile(img_byte_arr.getvalue()), save=False)
    despiece.save()

    # 4. Eliminar ítems anteriores y recrear con vinculación al catálogo Producto
    despiece.items.all().delete()

    # Mapeo por SKU para vinculación instantánea
    skus = [r['codigo_articulo'] for r in rows_parsed]
    productos_map = {
        p.codigo_articulo: p for p in Producto.objects.filter(codigo_articulo__in=skus)
    }

    items_to_create = []
    for row in rows_parsed:
        prod = productos_map.get(row['codigo_articulo'])
        items_to_create.append(DespieceItem(
            despiece=despiece,
            posicion=row['posicion'],
            codigo_articulo=row['codigo_articulo'],
            descripcion=row['descripcion'],
            cantidad=row['cantidad'],
            producto=prod,
        ))

    DespieceItem.objects.bulk_create(items_to_create)
    despiece.total_partes = len(items_to_create)
    despiece.save(update_fields=['total_partes'])

    return despiece


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
