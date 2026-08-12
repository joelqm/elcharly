"""Conversión de imágenes a WebP para catálogo web."""
from __future__ import annotations

import io
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None


def convertir_a_webp(archivo: UploadedFile, max_lado: int = 1600, calidad: int = 82) -> ContentFile:
    """
    Convierte una imagen subida a WebP (RGB, orientada, redimensionada).
    Si Pillow no está disponible, reenvía el archivo original.
    """
    nombre_base = Path(getattr(archivo, 'name', 'imagen') or 'imagen').stem
    if Image is None:
        data = archivo.read()
        if hasattr(archivo, 'seek'):
            archivo.seek(0)
        return ContentFile(data, name=f'{nombre_base}.webp')

    archivo.seek(0)
    img = Image.open(archivo)
    img = ImageOps.exif_transpose(img)
    if img.mode in ('RGBA', 'P'):
        fondo = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        fondo.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = fondo
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    img.thumbnail((max_lado, max_lado), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='WEBP', quality=calidad, method=6)
    return ContentFile(buf.getvalue(), name=f'{nombre_base}.webp')
