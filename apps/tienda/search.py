"""Búsqueda por tokens: «carbon 132» encuentra «CARBON CB-132» y «CARBÓN GENÉRICO»."""
from __future__ import annotations

import re
import unicodedata

from django.db.models import Q, QuerySet


def normalizar_texto_busqueda(texto: str) -> str:
    """Minúsculas, sin tildes ni ñ especial — apto para índice de búsqueda."""
    if not texto:
        return ''
    s = unicodedata.normalize('NFD', str(texto))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.lower()
    s = re.sub(r'[-_/.,;:+]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def tokens_busqueda(texto: str) -> list[str]:
    """Parte la consulta en palabras (ignora vacíos y símbolos sueltos)."""
    return [t for t in normalizar_texto_busqueda(texto).split() if t]


def filtrar_por_tokens(qs: QuerySet, q: str, campos: list[str]) -> QuerySet:
    """
    Cada token debe aparecer en al menos uno de los campos (AND entre tokens).
    Ejemplo: carbon 132 → nombre contiene carbon Y (nombre|codigo|modelo) contiene 132.
    """
    toks = tokens_busqueda(q)
    if not toks:
        return qs
    for tok in toks:
        clause = Q()
        for campo in campos:
            clause |= Q(**{f'{campo}__icontains': tok})
        qs = qs.filter(clause)
    return qs


def filtrar_productos(qs: QuerySet, q: str) -> QuerySet:
    """Atajo para catálogo de productos (incluye nombre normalizado sin tildes)."""
    toks = tokens_busqueda(q)
    if not toks:
        return qs
    for tok in toks:
        clause = (
            Q(nombre__icontains=tok)
            | Q(codigo_articulo__icontains=tok)
            | Q(modelo__icontains=tok)
            | Q(nombre_busqueda__icontains=tok)
        )
        qs = qs.filter(clause)
    return qs
