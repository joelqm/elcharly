"""Correos transaccionales (SMTP / consola en desarrollo)."""
import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _enviar(asunto, mensaje, destinatario):
    if not destinatario:
        logger.info('Correo omitido (sin destinatario): %s', asunto)
        return False
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@elcharlymakita.pe')
    try:
        send_mail(
            subject=asunto,
            message=mensaje,
            from_email=from_email,
            recipient_list=[destinatario],
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.exception('Error enviando correo a %s: %s', destinatario, e)
        return False


def enviar_confirmacion_compra(pedido):
    cliente = pedido.cliente
    lineas = [
        f'Hola {cliente.nombre_completo},',
        '',
        f'Su pedido {pedido.numero_pedido} fue confirmado correctamente.',
        f'Total: S/ {pedido.total:.2f}',
        f'Dirección de envío: {pedido.direccion_envio or "Retiro en tienda"}',
        '',
        'Detalle:',
    ]
    for d in pedido.detalles.select_related('producto'):
        lineas.append(
            f'  - {d.cantidad} x {d.producto.nombre} (S/ {d.subtotal:.2f})'
        )
    lineas.extend([
        '',
        'Gracias por comprar en Charly Makita — Arequipa.',
        'Recojo en tienda: Galería ASPYME, 2do Piso (Óvalo Mariscal Castilla).',
        'WhatsApp: 960 160 842',
    ])
    return _enviar(
        asunto=f'Confirmación de compra {pedido.numero_pedido} — Charly Makita',
        mensaje='\n'.join(lineas),
        destinatario=cliente.correo,
    )


def enviar_alerta_retiro(mantenimiento):
    cliente = mantenimiento.equipo.cliente
    equipo = mantenimiento.equipo
    prod_name = (
        equipo.producto.nombre if equipo.producto else equipo.modelo_alternativo
    )
    mensaje = (
        f'Hola {cliente.nombre_completo},\n\n'
        f'Le informamos que el servicio técnico de su equipo «{prod_name}» '
        f'(Serie: {equipo.numero_serie}) está listo para retiro.\n\n'
        f'Puede pasar a retirarlo en nuestra tienda: Galería ASPYME, 2do Piso '
        f'(Óvalo Mariscal Castilla), Arequipa.\n'
        f'Taller: Galería Divino Jesús, Pasaje Santa Catalina 100, Int. 16.\n\n'
        f'WhatsApp: 960 160 842\n\n'
        f'Charly Makita — Servicio Técnico Autorizado.'
    )
    return _enviar(
        asunto=f'Su {prod_name} está listo para retiro — Charly Makita',
        mensaje=mensaje,
        destinatario=cliente.correo,
    )
