from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.contrib import messages
from .models import Cliente
from apps.pedidos.models import Pedido
from apps.mantenimiento.models import EquipoRegistrado, Mantenimiento

def crm_required(view_func):
    """
    Decorator to restrict view access to Admins, Sellers (Vendedores), and Technicians.
    """
    def _wrapped_view(request, *args, **kwargs):
        from apps.sistema.internal_access import (
            is_staff_interno,
            ocultar_sistema_interno,
            redirect_pos_login,
        )

        if not request.user.is_authenticated:
            return redirect_pos_login(request)
        if not is_staff_interno(request.user):
            return ocultar_sistema_interno(request)
        allowed_roles = [request.user.ROLE_ADMIN, request.user.ROLE_VENDEDOR, request.user.ROLE_TECNICO]
        if request.user.rol not in allowed_roles and not request.user.is_superuser:
            return ocultar_sistema_interno(request)
        return view_func(request, *args, **kwargs)
    return _wrapped_view

@crm_required
def cliente_lista(request):
    """
    List and search clients.
    """
    query = request.GET.get('q', '').strip()
    etiqueta_filter = request.GET.get('etiqueta', '').strip()
    
    clientes = Cliente.objects.all().order_by('nombre_completo')
    
    if query:
        from apps.tienda.search import filtrar_por_tokens
        clientes = filtrar_por_tokens(
            clientes, query,
            ['nombre_completo', 'dni_ruc', 'telefono', 'correo'],
        )
        
    if etiqueta_filter:
        clientes = clientes.filter(etiqueta=etiqueta_filter)
        
    context = {
        'clientes': clientes,
        'query': query,
        'etiqueta_filter': etiqueta_filter,
        'etiquetas': Cliente.ETIQUETA_CHOICES,
    }
    return render(request, 'clientes/lista.html', context)

@crm_required
def cliente_detalle(request, cliente_id):
    """
    Ficha completa of a client: stats, details, edit form, purchases, and equipment.
    """
    cliente = get_object_or_404(Cliente, id=cliente_id)
    
    if request.method == 'POST':
        # Process the form update
        cliente.nombre_completo = request.POST.get('nombre_completo', '').strip()
        cliente.dni_ruc = request.POST.get('dni_ruc', '').strip()
        cliente.telefono = request.POST.get('telefono', '').strip()
        cliente.correo = request.POST.get('correo', '').strip()
        cliente.direccion = request.POST.get('direccion', '').strip()
        cliente.ciudad = request.POST.get('ciudad', '').strip()
        cliente.etiqueta = request.POST.get('etiqueta', cliente.etiqueta)
        cliente.notas = request.POST.get('notas', '').strip()
        
        # Simple validation
        if not cliente.nombre_completo or not cliente.dni_ruc:
            messages.error(request, "Nombre completo y DNI/RUC son obligatorios.")
        else:
            try:
                # Check uniqueness if changed DNI/RUC
                exists = Cliente.objects.exclude(id=cliente.id).filter(dni_ruc=cliente.dni_ruc).exists()
                if exists:
                    messages.error(request, "Ya existe otro cliente registrado con este DNI/RUC.")
                else:
                    cliente.save()
                    messages.success(request, "Ficha del cliente actualizada exitosamente.")
                    return redirect('clientes:detalle', cliente_id=cliente.id)
            except Exception as e:
                messages.error(request, f"Error al guardar los datos: {str(e)}")

    # Fetch history data
    pedidos = Pedido.objects.filter(cliente=cliente).order_by('-fecha_pedido')
    equipos = EquipoRegistrado.objects.filter(cliente=cliente).select_related('producto').order_by('-fecha_compra')
    
    # Get all maintenance records for these equipments
    mantenimientos = Mantenimiento.objects.filter(equipo__cliente=cliente).select_related('equipo', 'tecnico').order_by('-fecha_ingreso')
    
    # Count of equipments currently in maintenance
    equipos_en_mantenimiento = equipos.filter(estado=EquipoRegistrado.ESTADO_MANTENIMIENTO).count()

    context = {
        'cliente': cliente,
        'pedidos': pedidos,
        'equipos': equipos,
        'mantenimientos': mantenimientos,
        'equipos_en_mantenimiento': equipos_en_mantenimiento,
        'etiquetas': Cliente.ETIQUETA_CHOICES,
        'tipos': Cliente.TIPO_CHOICES,
    }
    return render(request, 'clientes/detalle.html', context)

@crm_required
def cliente_crear(request):
    """
    Create a new client manually in the CRM.
    """
    if request.method == 'POST':
        nombre_completo = request.POST.get('nombre_completo', '').strip()
        tipo = request.POST.get('tipo', Cliente.TIPO_PERSONA)
        dni_ruc = request.POST.get('dni_ruc', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        correo = request.POST.get('correo', '').strip()
        direccion = request.POST.get('direccion', '').strip()
        ciudad = request.POST.get('ciudad', 'Arequipa').strip()
        etiqueta = request.POST.get('etiqueta', Cliente.ETIQUETA_NUEVO)
        notas = request.POST.get('notas', '').strip()
        
        if not nombre_completo or not dni_ruc:
            messages.error(request, "Nombre completo y DNI/RUC son obligatorios.")
        else:
            if Cliente.objects.filter(dni_ruc=dni_ruc).exists():
                messages.error(request, "Ya existe un cliente con ese DNI/RUC.")
            else:
                cliente = Cliente.objects.create(
                    nombre_completo=nombre_completo,
                    tipo=tipo,
                    dni_ruc=dni_ruc,
                    telefono=telefono,
                    correo=correo,
                    direccion=direccion,
                    ciudad=ciudad,
                    canal_origen=Cliente.CANAL_POS,  # Manual register in store
                    etiqueta=etiqueta,
                    notas=notas
                )
                messages.success(request, "Cliente registrado exitosamente en el CRM.")
                return redirect('clientes:detalle', cliente_id=cliente.id)
                
    context = {
        'etiquetas': Cliente.ETIQUETA_CHOICES,
        'tipos': Cliente.TIPO_CHOICES,
    }
    return render(request, 'clientes/crear.html', context)
