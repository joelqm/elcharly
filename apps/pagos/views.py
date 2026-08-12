from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST

from apps.pagos.models import Pago
from apps.pedidos.models import Pedido
from apps.pedidos.services import confirmar_pago_pedido, StockInsuficienteError
from apps.inventario.models import MovimientoInventario
from proyecto_makita.email_utils import enviar_confirmacion_compra


def pagos_staff_required(view_func):
    def _wrapped(request, *args, **kwargs):
        from apps.sistema.internal_access import (
            ocultar_sistema_interno,
            puede_usar_pos,
            redirect_pos_login,
        )

        if not request.user.is_authenticated:
            return redirect_pos_login(request)
        if not puede_usar_pos(request.user):
            return ocultar_sistema_interno(request)
        return view_func(request, *args, **kwargs)
    return _wrapped


@pagos_staff_required
def lista_pagos_pendientes(request):
    pagos = (
        Pago.objects.filter(estado=Pago.ESTADO_PENDIENTE)
        .select_related('pedido', 'pedido__cliente')
        .order_by('-fecha_pago')
    )
    return render(
        request,
        'pagos/lista_pendientes.html',
        {'pagos': pagos},
    )


@pagos_staff_required
@require_POST
def aprobar_pago(request, pago_id):
    pago = get_object_or_404(Pago, id=pago_id)
    if pago.estado != Pago.ESTADO_PENDIENTE:
        messages.warning(request, 'Este pago ya no está pendiente.')
        return redirect('pagos:lista_pendientes')

    pedido = pago.pedido
    referencia = request.POST.get('referencia', '').strip() or f'MANUAL-{pago.id}'

    try:
        confirmar_pago_pedido(
            pedido=pedido,
            metodo=pago.metodo,
            monto=pago.monto,
            referencia_externa=referencia,
            usuario=request.user,
            motivo_inventario=MovimientoInventario.MOTIVO_VENTA_WEB,
            pago=pago,
        )
        try:
            enviar_confirmacion_compra(pedido)
        except Exception:
            pass
        messages.success(
            request,
            f'Pago del pedido {pedido.numero_pedido} aprobado. Stock e inventario actualizados.',
        )
    except StockInsuficienteError as e:
        messages.error(request, e.mensaje)

    return redirect('pagos:lista_pendientes')


@pagos_staff_required
@require_POST
def rechazar_pago(request, pago_id):
    pago = get_object_or_404(Pago, id=pago_id)
    if pago.estado != Pago.ESTADO_PENDIENTE:
        messages.warning(request, 'Este pago ya no está pendiente.')
        return redirect('pagos:lista_pendientes')

    pago.estado = Pago.ESTADO_RECHAZADO
    pago.save(update_fields=['estado'])

    pedido = pago.pedido
    if pedido.estado == Pedido.ESTADO_PENDIENTE:
        pedido.estado = Pedido.ESTADO_CANCELADO
        pedido.save(update_fields=['estado'])

    messages.info(
        request,
        f'Pago del pedido {pedido.numero_pedido} rechazado y pedido cancelado.',
    )
    return redirect('pagos:lista_pendientes')
