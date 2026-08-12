from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.conf import settings
from django.views.decorators.http import require_POST
import json
import logging

from apps.tienda.cart import Cart
from apps.clientes.models import Cliente
from .models import Pedido, DetallePedido
from apps.pagos.models import Pago
from .services import (
    confirmar_pago_pedido,
    validar_stock_carrito,
    StockInsuficienteError,
    reservar_stock_web,
)
from apps.inventario.models import MovimientoInventario
from urllib.parse import quote

logger = logging.getLogger(__name__)


def _whatsapp_pago_url(pedido):
    negocio = getattr(settings, 'NEGOCIO', {})
    wa = (negocio.get('whatsapp') or '51960160842').replace('+', '').replace(' ', '')
    lineas = [
        f'Hola, adjunto mi voucher de pago.',
        f'Pedido: {pedido.numero_pedido}',
        f'Total: S/ {pedido.total}',
        f'Cliente: {pedido.cliente.nombre_completo}',
        f'DNI/RUC: {pedido.cliente.dni_ruc}',
        f'Tel: {pedido.cliente.telefono or "-"}',
        '',
        'Detalle:',
    ]
    for d in pedido.detalles.select_related('producto')[:20]:
        lineas.append(f'- {d.producto.nombre} ×{d.cantidad}')
    lineas.append('')
    lineas.append('(Envío captura de Yape / transferencia)')
    return f'https://wa.me/{wa}?text={quote(chr(10).join(lineas))}'


def checkout(request):
    cart = Cart(request)
    if len(cart) == 0:
        return redirect('tienda:cart_detail')

    errores_stock = validar_stock_carrito(cart)
    if errores_stock and request.method != 'POST':
        for err in errores_stock:
            messages.warning(request, err)

    if request.method == 'POST':
        errores_stock = validar_stock_carrito(cart)
        if errores_stock:
            for err in errores_stock:
                messages.error(request, err)
            return redirect('tienda:cart_detail')

        nombre_completo = request.POST.get('nombre_completo')
        dni_ruc = request.POST.get('dni_ruc')
        telefono = request.POST.get('telefono')
        correo = request.POST.get('correo')
        metodo_pago = request.POST.get('metodo_pago')
        notas = request.POST.get('notas')
        # Solo recojo en tienda (delivery deshabilitado)
        negocio = getattr(settings, 'NEGOCIO', {})
        direccion_envio = f"RECOJO EN TIENDA — {negocio.get('direccion', 'Galería ASPYME, 2do Piso (Óvalo Mariscal Castilla), Arequipa')}"

        if not all([nombre_completo, dni_ruc, telefono, correo, metodo_pago]):
            messages.error(request, 'Complete todos los campos obligatorios.')
            return render(request, 'pedidos/checkout.html', {'cart': cart})

        if metodo_pago not in ('yape', 'plin', 'tienda'):
            messages.error(request, 'Elige Yape/Plin o pagar en tienda.')
            return render(request, 'pedidos/checkout.html', {'cart': cart})

        cliente, created = Cliente.objects.get_or_create(
            dni_ruc=dni_ruc.strip(),
            defaults={
                'nombre_completo': nombre_completo.strip(),
                'telefono': telefono.strip(),
                'correo': correo.strip(),
                'direccion': negocio.get('direccion', ''),
                'canal_origen': Cliente.CANAL_WEB,
            },
        )
        if not created:
            cliente.nombre_completo = nombre_completo.strip()
            cliente.telefono = telefono.strip()
            cliente.correo = correo.strip()
            cliente.save()

        total = cart.get_total()
        igv = cart.get_igv()
        subtotal = total - igv

        notas_final = (notas or '').strip()
        if notas_final:
            notas_final = f"{notas_final}\n[Recojo en tienda]"
        else:
            notas_final = '[Recojo en tienda]'

        with transaction.atomic():
            pedido = Pedido.objects.create(
                cliente=cliente,
                canal=Pedido.CANAL_WEB,
                estado=Pedido.ESTADO_PENDIENTE,
                subtotal=subtotal,
                igv=igv,
                total=total,
                direccion_envio=direccion_envio,
                notas=notas_final,
            )
            for item in cart:
                prod = item['producto']
                DetallePedido.objects.create(
                    pedido=pedido,
                    producto=prod,
                    codigo_articulo=prod.codigo_articulo,
                    nombre_producto=prod.nombre_publico if hasattr(prod, 'nombre_publico') else prod.nombre,
                    cantidad=item['cantidad'],
                    precio_unitario=item['precio'],
                )

        request.session['order_id'] = pedido.id

        # Yape / Plin / pagar en tienda → reserva 24h
        horas = int(getattr(settings, 'NEGOCIO', {}).get('pedido_reserva_horas', 24) or 24)
        try:
            reservar_stock_web(pedido, horas=horas)
        except StockInsuficienteError as e:
            pedido.delete()
            messages.error(request, e.mensaje)
            return redirect('tienda:cart_detail')

        metodo = metodo_pago if metodo_pago in dict(Pago.METODO_CHOICES) else Pago.METODO_YAPE
        pago = Pago.objects.create(
            pedido=pedido,
            metodo=metodo,
            monto=total,
            estado=Pago.ESTADO_PENDIENTE,
        )

        # Voucher solo al confirmar (Yape/Plin) → WebP en pedido y pago
        voucher = request.FILES.get('voucher')
        if voucher and metodo_pago in ('yape', 'plin'):
            try:
                from django.core.files.base import ContentFile
                from apps.tienda.images import convertir_a_webp
                webp = convertir_a_webp(voucher)
                data = webp.read()
                pedido.voucher.save(webp.name, ContentFile(data), save=True)
                pago.voucher.save(webp.name, ContentFile(data), save=True)
            except Exception:
                pedido.voucher = voucher
                pedido.save(update_fields=['voucher'])
                pago.voucher = voucher
                pago.save(update_fields=['voucher'])

        cart.clear()
        return redirect('pedidos:pago_manual_instrucciones')

    return render(request, 'pedidos/checkout.html', {'cart': cart})



def pago_exitoso(request):
    pedido_id = request.session.get('order_id')
    pedido = None
    if pedido_id:
        pedido = Pedido.objects.filter(id=pedido_id).first()
        if 'order_id' in request.session:
            del request.session['order_id']

    return render(request, 'pedidos/pago_exitoso.html', {'pedido': pedido})


def pago_manual_instrucciones(request):
    pedido_id = request.session.get('order_id')
    pedido = Pedido.objects.filter(id=pedido_id).first() if pedido_id else None
    negocio = getattr(settings, 'NEGOCIO', {})
    whatsapp_url = _whatsapp_pago_url(pedido) if pedido else '#'
    ultimo_pago = pedido.pagos.order_by('-fecha_pago').first() if pedido else None
    metodo = ultimo_pago.metodo if ultimo_pago else 'yape'
    return render(request, 'pedidos/pago_manual.html', {
        'pedido': pedido,
        'negocio': negocio,
        'whatsapp_url': whatsapp_url,
        'reserva_horas': negocio.get('pedido_reserva_horas', 24),
        'es_tienda': metodo == 'tienda',
        'metodo_pago': metodo,
    })


@require_POST
def subir_voucher(request):
    """Cliente sube captura de pago (opcional; también puede ir por WhatsApp)."""
    pedido_id = request.session.get('order_id') or request.POST.get('pedido_id')
    pedido = get_object_or_404(Pedido, id=pedido_id, estado=Pedido.ESTADO_PENDIENTE)
    archivo = request.FILES.get('voucher')
    if not archivo:
        messages.error(request, 'Selecciona una imagen del voucher.')
        return redirect('pedidos:pago_manual_instrucciones')
    if archivo.size > 5 * 1024 * 1024:
        messages.error(request, 'El archivo no debe superar 5 MB.')
        return redirect('pedidos:pago_manual_instrucciones')
    try:
        from apps.tienda.images import convertir_a_webp
        webp = convertir_a_webp(archivo)
        pedido.voucher.save(webp.name, webp, save=True)
    except Exception:
        pedido.voucher = archivo
        pedido.save(update_fields=['voucher'])
    messages.success(request, 'Voucher recibido. Validaremos tu pago pronto.')
    return redirect('pedidos:pago_manual_instrucciones')


def seguimiento_pedido(request):
    """Consulta pública de pedidos por DNI + teléfono (sin crear cuenta)."""
    pedidos = None
    buscado = False
    dni = ''
    telefono = ''

    if request.method == 'POST':
        buscado = True
        dni = (request.POST.get('dni_ruc') or '').strip()
        telefono = (request.POST.get('telefono') or '').strip()
        if not dni or not telefono:
            messages.error(request, 'Ingrese DNI/RUC y teléfono.')
        else:
            cliente = Cliente.objects.filter(dni_ruc=dni).first()
            if not cliente or (cliente.telefono or '').strip() != telefono:
                messages.error(
                    request,
                    'No encontramos pedidos con esos datos. Verifique DNI y teléfono.',
                )
            else:
                pedidos = (
                    Pedido.objects.filter(cliente=cliente)
                    .prefetch_related('detalles__producto')
                    .order_by('-fecha_pedido')[:30]
                )
                if not pedidos:
                    messages.info(request, 'Aún no hay pedidos registrados con esos datos.')

    return render(
        request,
        'pedidos/seguimiento.html',
        {
            'pedidos': pedidos,
            'buscado': buscado,
            'dni': dni,
            'telefono': telefono,
        },
    )


def _staff_pedidos_required(view_func):
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


@_staff_pedidos_required
def lista_pedidos_staff(request):
    estado = request.GET.get('estado', '')
    pedidos = Pedido.objects.select_related('cliente').prefetch_related('pagos')
    if estado:
        pedidos = pedidos.filter(estado=estado)
    else:
        pedidos = pedidos.exclude(estado=Pedido.ESTADO_CANCELADO)
    pedidos = pedidos[:100]
    return render(
        request,
        'pedidos/lista_staff.html',
        {'pedidos': pedidos, 'estado_filtro': estado, 'estados': Pedido.ESTADO_CHOICES},
    )


@_staff_pedidos_required
@require_POST
def cambiar_estado_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    nuevo = request.POST.get('estado')
    validos = {c[0] for c in Pedido.ESTADO_CHOICES}
    if nuevo not in validos:
        messages.error(request, 'Estado inválido.')
        return redirect('pedidos:lista_staff')

    permitidas = {
        Pedido.ESTADO_PENDIENTE: {Pedido.ESTADO_CANCELADO},
        Pedido.ESTADO_PAGADO: {Pedido.ESTADO_ENVIADO, Pedido.ESTADO_ENTREGADO, Pedido.ESTADO_CANCELADO},
        Pedido.ESTADO_ENVIADO: {Pedido.ESTADO_ENTREGADO},
        Pedido.ESTADO_ENTREGADO: set(),
        Pedido.ESTADO_CANCELADO: set(),
    }
    if nuevo not in permitidas.get(pedido.estado, set()) and nuevo != pedido.estado:
        messages.error(
            request,
            f'No se puede pasar de «{pedido.get_estado_display()}» a ese estado.',
        )
        return redirect('pedidos:lista_staff')

    pedido.estado = nuevo
    pedido.save(update_fields=['estado'])
    messages.success(
        request,
        f'Pedido {pedido.numero_pedido} actualizado a «{pedido.get_estado_display()}».',
    )
    return redirect('pedidos:lista_staff')


def _enviar_confirmacion_compra(pedido):
    from proyecto_makita.email_utils import enviar_confirmacion_compra
    try:
        enviar_confirmacion_compra(pedido)
    except Exception as e:
        logger.warning('No se pudo enviar correo de confirmación: %s', e)
