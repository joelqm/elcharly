"""PDF de cotización formato STA (oficial / moderno)."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# Ancho útil A4 con márgenes 14 mm
PAGE_W = 182 * mm
MAKITA_TEAL = colors.HexColor('#009B94')
INK = colors.HexColor('#0F172A')
MUTED = colors.HexColor('#64748B')
LINE = colors.HexColor('#CBD5E1')
HEADER_BG = colors.HexColor('#0F172A')
LABEL_BG = colors.HexColor('#F1F5F9')
TOTAL_BG = colors.HexColor('#ECFDF5')
MAKITA_RED = colors.HexColor('#C41E3A')

_SCRIPT_REGISTERED = False


def _ensure_script_font() -> str:
    global _SCRIPT_REGISTERED
    name = 'ElCharlyScript'
    if _SCRIPT_REGISTERED:
        return name
    candidates = [
        Path(settings.BASE_DIR) / 'static' / 'fonts' / 'script.ttf',
        Path('/app/static/fonts/script.ttf'),
    ]
    for path in candidates:
        if path.is_file():
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
                _SCRIPT_REGISTERED = True
                return name
            except Exception:
                continue
    return 'Helvetica-Oblique'


def _logo_flowable():
    path = Path(settings.MEDIA_ROOT) / 'logo_makita.png'
    if not path.is_file():
        path = Path(settings.BASE_DIR) / 'media' / 'logo_makita.png'
    if path.is_file():
        try:
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(str(path))
            orig_w, orig_h = ir.getSize()
            target_w = 40 * mm
            target_h = target_w * (orig_h / orig_w)
            if target_h > 16 * mm:
                target_h = 16 * mm
                target_w = target_h * (orig_w / orig_h)
            img = Image(str(path), width=target_w, height=target_h)
            img.hAlign = 'LEFT'
            return img
        except Exception:
            img = Image(str(path), width=38 * mm, height=10 * mm)
            img.hAlign = 'LEFT'
            return img
    styles = getSampleStyleSheet()
    s = ParagraphStyle(
        'logo_fb', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=12, textColor=MAKITA_RED, leading=14,
    )
    return Paragraph('Makita<br/><font size="7" color="#64748B">Ventas y Servicio Técnico</font>', s)


def exportar_cotizacion_pdf(cotizacion) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=f"Cotización {cotizacion.numero}",
        author="Servicio Técnico Autorizado Makita - El Charly",
    )
    styles = getSampleStyleSheet()
    script = _ensure_script_font()

    s_title = ParagraphStyle(
        't', parent=styles['Normal'], fontName='Helvetica-Bold',
        fontSize=18, alignment=TA_CENTER, textColor=INK, leading=20,
    )
    s_sta = ParagraphStyle(
        'sta', parent=styles['Normal'], fontName='Helvetica-Bold',
        fontSize=8, alignment=TA_CENTER, textColor=MUTED, leading=11,
    )
    s_script = ParagraphStyle(
        'scr', parent=styles['Normal'], fontName=script,
        fontSize=16, alignment=TA_CENTER, textColor=MAKITA_TEAL, leading=18,
    )
    s_small = ParagraphStyle('sm', parent=styles['Normal'], fontSize=8, leading=10, textColor=INK)
    s_label = ParagraphStyle(
        'lb', parent=styles['Normal'], fontName='Helvetica-Bold',
        fontSize=7.5, leading=9, textColor=MUTED,
    )
    s_cell = ParagraphStyle('c', parent=styles['Normal'], fontSize=8, leading=10, textColor=INK)
    s_center = ParagraphStyle('cc', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, textColor=INK)
    s_th = ParagraphStyle(
        'th', parent=styles['Normal'], fontName='Helvetica-Bold',
        fontSize=7.5, alignment=TA_CENTER, textColor=colors.white, leading=9,
    )
    s_foot = ParagraphStyle(
        'f', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER,
        leading=13, textColor=INK,
    )
    s_foot_muted = ParagraphStyle(
        'fm', parent=styles['Normal'], fontSize=8.5, alignment=TA_CENTER,
        leading=12, textColor=MUTED,
    )

    story = []

    # —— Cabecera (mismo ancho que tablas) ——
    meta = [
        [Paragraph('CÓDIGO', s_label), Paragraph(f'<b>{cotizacion.numero}</b>', s_small)],
        [Paragraph('FECHA', s_label), Paragraph(cotizacion.fecha_creacion.strftime('%d/%m/%Y'), s_small)],
    ]
    meta_t = Table(meta, colWidths=[22 * mm, 42 * mm])
    meta_t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, LINE),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (0, -1), LABEL_BG),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))

    title_block = Table(
        [
            [Paragraph('COTIZACIÓN', s_title)],
            [Paragraph('SERVICIO TÉCNICO AUTORIZADO', s_sta)],
            [Paragraph('El Charly', s_script)],
        ],
        colWidths=[PAGE_W - 42 * mm - 64 * mm],
    )
    title_block.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))

    head = Table(
        [[_logo_flowable(), title_block, meta_t]],
        colWidths=[42 * mm, PAGE_W - 42 * mm - 64 * mm, 64 * mm],
    )
    head.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('LINEBELOW', (0, 0), (-1, -1), 1.2, MAKITA_TEAL),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(head)
    story.append(Spacer(1, 5 * mm))

    # —— Cliente (Grid de 2 columnas) ——
    cli = [
        [
            Paragraph('CLIENTE', s_label), Paragraph(f'<b>{cotizacion.cliente_nombre or "—"}</b>', s_small),
            Paragraph('DIRECCIÓN', s_label), Paragraph(cotizacion.cliente_direccion or '—', s_small)
        ],
        [
            Paragraph('N° DE DOCUMENTO', s_label), Paragraph(cotizacion.cliente_ruc or '—', s_small),
            Paragraph('N° CELULAR', s_label), Paragraph(cotizacion.cliente_telefono or '—', s_small)
        ],
    ]
    cli_t = Table(cli, colWidths=[32 * mm, 59 * mm, 28 * mm, 63 * mm])
    cli_t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.7, LINE),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, LINE),
        ('BACKGROUND', (0, 0), (0, -1), LABEL_BG),
        ('BACKGROUND', (2, 0), (2, -1), LABEL_BG),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(cli_t)
    story.append(Spacer(1, 4 * mm))

    # —— Ítems ——
    detalles = list(cotizacion.detalles.all().select_related('repuesto'))
    
    # Pre-cargar imágenes y determinar si al menos un ítem posee foto válida
    item_images = []
    for d in detalles:
        img_flowable = None
        if d.repuesto_id:
            img_field = None
            gal_principal = d.repuesto.imagenes.filter(es_principal=True).first()
            if gal_principal and gal_principal.imagen:
                img_field = gal_principal.imagen
            elif d.repuesto.imagen_principal:
                img_field = d.repuesto.imagen_principal
            elif d.repuesto.imagenes.exists():
                img_field = d.repuesto.imagenes.first().imagen

            if img_field:
                try:
                    fpath = Path(settings.MEDIA_ROOT) / str(img_field)
                    if fpath.is_file():
                        img_flowable = Image(str(fpath), width=12 * mm, height=12 * mm)
                        img_flowable.hAlign = 'CENTER'
                except Exception:
                    pass
        item_images.append(img_flowable)

    tiene_imagenes = any(img is not None for img in item_images)

    if tiene_imagenes:
        col_w = [10 * mm, 18 * mm, 24 * mm, 68 * mm, 28 * mm, 14 * mm, 20 * mm]  # = 182 mm
        header_row = [
            Paragraph('ÍTEM', s_th),
            Paragraph('IMAGEN', s_th),
            Paragraph('CÓDIGO', s_th),
            Paragraph('DESCRIPCIÓN', s_th),
            Paragraph('PRECIO UNITARIO', s_th),
            Paragraph('CANT.', s_th),
            Paragraph('SUBTOTAL', s_th),
        ]
    else:
        col_w = [12 * mm, 28 * mm, 78 * mm, 30 * mm, 14 * mm, 20 * mm]  # = 182 mm
        header_row = [
            Paragraph('ÍTEM', s_th),
            Paragraph('CÓDIGO', s_th),
            Paragraph('DESCRIPCIÓN', s_th),
            Paragraph('PRECIO UNITARIO', s_th),
            Paragraph('CANT.', s_th),
            Paragraph('SUBTOTAL', s_th),
        ]

    s_total_label = ParagraphStyle(
        'TotalLabel', parent=styles['Normal'], fontSize=9, leading=12,
        alignment=TA_RIGHT, textColor=INK, fontName='Helvetica-Bold'
    )

    data = [header_row]

    for i, d in enumerate(detalles, start=1):
        row_cells = [Paragraph(str(i), s_center)]
        if tiene_imagenes:
            row_cells.append(item_images[i - 1] or Paragraph('—', s_center))
        
        if d.cantidad > 0:
            p_unit_str = f'S/ {Decimal(d.precio_unitario):,.2f}'
            cant_str = str(d.cantidad)
            sub_str = f'S/ {Decimal(d.subtotal):,.2f}'
        else:
            p_unit_str = '—'
            cant_str = '—'
            sub_str = '—'

        row_cells.extend([
            Paragraph(d.codigo_linea or '—', s_center),
            Paragraph(d.descripcion_linea, s_cell),
            Paragraph(p_unit_str, s_center),
            Paragraph(cant_str, s_center),
            Paragraph(sub_str, s_center),
        ])
        data.append(row_cells)

    num_cols = len(header_row)
    for _ in range(max(0, 8 - len(detalles))):
        data.append([''] * num_cols)

    span_until = num_cols - 2
    total_col = num_cols - 1
    total_row = [''] * num_cols
    total_row[0] = Paragraph('<b>Total:</b>', s_total_label)
    total_row[total_col] = Paragraph(f'<b>S/ {Decimal(cotizacion.total):,.2f}</b>', s_center)
    data.append(total_row)

    t = Table(data, colWidths=col_w, repeatRows=1)
    last = len(data) - 1
    style_cmds = [
        ('BOX', (0, 0), (-1, last - 1), 0.7, LINE),
        ('INNERGRID', (0, 0), (-1, last - 1), 0.35, LINE),
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('SPAN', (0, last), (span_until, last)),
        ('BOX', (total_col, last), (total_col, last), 0.7, MAKITA_TEAL),
        ('INNERGRID', (total_col, last), (total_col, last), 0.4, MAKITA_TEAL),
        ('BACKGROUND', (total_col, last), (total_col, last), TOTAL_BG),
        ('BACKGROUND', (0, last), (span_until, last), colors.white),
    ]
    # Filas zebra
    for r in range(1, last):
        if r % 2 == 0 and any(data[r]):
            style_cmds.append(('BACKGROUND', (0, r), (-1, r), colors.HexColor('#F8FAFC')))
    t.setStyle(TableStyle(style_cmds))
    story.append(t)
    story.append(Spacer(1, 8 * mm))

    # —— Observaciones editables ——
    obs = cotizacion.lineas_observaciones()
    for i, line in enumerate(obs):
        sty = s_foot if i == 0 or i == len(obs) - 1 else s_foot_muted
        if i == 0:
            story.append(Paragraph(f'<b>{line}</b>', s_foot))
        else:
            story.append(Paragraph(line, sty))
        story.append(Spacer(1, 1.5 * mm))

    doc.build(story)
    return buffer.getvalue()
