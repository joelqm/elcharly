from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.pedidos.models import Pedido
from apps.pedidos.services import liberar_reserva_pedido


class Command(BaseCommand):
    help = 'Libera pedidos web pendientes cuya reserva (24h) expiró.'

    def handle(self, *args, **options):
        ahora = timezone.now()
        qs = Pedido.objects.filter(
            estado=Pedido.ESTADO_PENDIENTE,
            canal=Pedido.CANAL_WEB,
            reservado_hasta__lt=ahora,
        )
        n = 0
        for pedido in qs.iterator():
            if liberar_reserva_pedido(pedido):
                n += 1
                self.stdout.write(f'Liberado {pedido.numero_pedido}')
        self.stdout.write(self.style.SUCCESS(f'{n} pedido(s) liberados.'))
