"""
Migra correlativos legados a formato estilo SUNAT.

Antes:  VTA-2026-0001  /  T-2026-00001
Ahora:  R001-00000001  (recibo/ticket interno)

Uso:
  python manage.py migrar_correlativos_sunat --dry-run
  python manage.py migrar_correlativos_sunat
"""
from __future__ import annotations

import re

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedidos.models import Pedido
from apps.pos.correlativos import SERIE_RECIBO, formatear_numero
from apps.pos.models import TicketPOS

_SUNAT_RE = re.compile(r'^[RBF][A-Z0-9]{3}-\d{1,8}$', re.I)
_LEGACY_TICKET = re.compile(r'^T-\d{4}-\d+$', re.I)
_LEGACY_VTA = re.compile(r'^VTA-\d{4}-\d+$', re.I)


def _es_sunat(num: str) -> bool:
    return bool(num and _SUNAT_RE.match(num.strip()))


def _es_legado(num: str) -> bool:
    n = (num or '').strip()
    if not n or _es_sunat(n):
        return False
    return bool(_LEGACY_TICKET.match(n) or _LEGACY_VTA.match(n) or n.startswith('T-') or n.startswith('VTA-'))


class Command(BaseCommand):
    help = 'Renumerar tickets/pedidos POS legados (VTA-/T-) a R001-00000001…'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra el plan, no escribe en BD.',
        )
        parser.add_argument(
            '--serie',
            default=SERIE_RECIBO,
            help='Serie destino (default R001).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry = options['dry_run']
        serie = (options['serie'] or SERIE_RECIBO).upper()

        # Conserva correlativos R001 ya emitidos; continúa después del máximo.
        existentes = list(
            TicketPOS.objects.filter(numero_serie__startswith=f'{serie}-')
            .values_list('numero_serie', flat=True)
        ) + list(
            Pedido.objects.filter(numero_pedido__startswith=f'{serie}-')
            .values_list('numero_pedido', flat=True)
        )
        max_n = 0
        for raw in existentes:
            m = re.match(rf'^{re.escape(serie)}-(\d+)$', str(raw), re.I)
            if m:
                max_n = max(max_n, int(m.group(1)))

        tickets = list(
            TicketPOS.objects.select_related('pedido')
            .order_by('fecha_emision', 'id')
        )
        pedidos_sin_ticket = list(
            Pedido.objects.filter(canal=Pedido.CANAL_POS, ticket_pos__isnull=True)
            .order_by('fecha_pedido', 'id')
        )

        plan = []
        next_n = max_n

        for t in tickets:
            if not _es_legado(t.numero_serie) and (
                not t.pedido_id or not _es_legado(t.pedido.numero_pedido)
            ):
                continue
            next_n += 1
            nuevo = formatear_numero(serie, next_n)
            plan.append(('ticket', t, nuevo))

        for p in pedidos_sin_ticket:
            if not _es_legado(p.numero_pedido):
                continue
            next_n += 1
            nuevo = formatear_numero(serie, next_n)
            plan.append(('pedido', p, nuevo))

        if not plan:
            self.stdout.write(self.style.SUCCESS('Nada que migrar: no hay correlativos legados.'))
            return

        self.stdout.write(f'Plan: {len(plan)} documento(s) → serie {serie} (desde {formatear_numero(serie, max_n + 1)})')
        for kind, obj, nuevo in plan[:30]:
            if kind == 'ticket':
                old_t = obj.numero_serie
                old_p = obj.pedido.numero_pedido if obj.pedido_id else '—'
                self.stdout.write(f'  Ticket #{obj.id}: {old_t} / pedido {old_p} → {nuevo}')
            else:
                self.stdout.write(f'  Pedido #{obj.id}: {obj.numero_pedido} → {nuevo}')
        if len(plan) > 30:
            self.stdout.write(f'  … y {len(plan) - 30} más')

        if dry:
            self.stdout.write(self.style.WARNING('Dry-run: no se guardó nada.'))
            transaction.set_rollback(True)
            return

        for kind, obj, nuevo in plan:
            if kind == 'ticket':
                TicketPOS.objects.filter(pk=obj.pk).update(numero_serie=nuevo)
                if obj.pedido_id:
                    Pedido.objects.filter(pk=obj.pedido_id).update(numero_pedido=nuevo)
            else:
                Pedido.objects.filter(pk=obj.pk).update(numero_pedido=nuevo)

        self.stdout.write(self.style.SUCCESS(f'Migrados {len(plan)} documento(s) a {serie}-…'))
