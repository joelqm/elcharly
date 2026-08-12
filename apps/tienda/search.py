"""Búsqueda por tokens: «carbon 132» encuentra «CARBON CB-132»."""
from __future__ import annotations

import re

from django.db.models import Q, QuerySet


def tokens_busqueda(texto: str) -> list[str]:
    """Parte la consulta en palabras (ignora vacíos y símbolos sueltos)."""
    if not texto:
        return []
    # Guiones/underscores se tratan como separadores para casar CB-132 con «132»
    normalizado = re.sub(r'[-_/.,;:+]+', ' ', str(texto).strip())
    return [t for t in normalizado.split() if t]


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
    """Atajo para catálogo de productos."""
    return filtrar_por_tokens(
        qs,
        q,
        ['nombre', 'codigo_articulo', 'modelo'],
    )
