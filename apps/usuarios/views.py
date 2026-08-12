from django.shortcuts import redirect, render
from django.contrib.auth.views import LoginView as BaseLoginView
from django.contrib.auth import logout, login
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.clientes.models import Cliente
from apps.pedidos.models import Pedido
from apps.mantenimiento.models import EquipoRegistrado
from .forms import RegistroClienteForm


class CustomLoginView(BaseLoginView):
    template_name = 'usuarios/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        if user.is_superuser or user.rol == 'admin':
            return reverse_lazy('pos:hub_inicio')
        elif user.rol == 'vendedor':
            return reverse_lazy('pos:hub_inicio')
        elif user.rol == 'tecnico':
            return reverse_lazy('mantenimiento:dashboard')
        else:
            return reverse_lazy('usuarios:mi_cuenta')


def custom_logout_view(request):
    logout(request)
    return redirect('tienda:catalogo')


def registro_cliente(request):
    if request.user.is_authenticated:
        return redirect('usuarios:mi_cuenta')

    if request.method == 'POST':
        form = RegistroClienteForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Vincular / crear ficha CRM
            Cliente.objects.get_or_create(
                dni_ruc=user.dni_ruc,
                defaults={
                    'nombre_completo': f'{user.first_name} {user.last_name}'.strip() or user.username,
                    'correo': user.email,
                    'telefono': user.telefono,
                    'canal_origen': Cliente.CANAL_WEB,
                },
            )
            login(request, user)
            messages.success(request, 'Cuenta creada correctamente. Bienvenido a Charly Makita.')
            return redirect('usuarios:mi_cuenta')
    else:
        form = RegistroClienteForm()

    return render(request, 'usuarios/registro.html', {'form': form})


@login_required
def dashboard_placeholder(request, dashboard):
    return render(request, 'usuarios/dashboard_placeholder.html', {'dashboard': dashboard})


@login_required
def mi_cuenta(request):
    user = request.user
    cliente = None
    if user.dni_ruc:
        cliente = Cliente.objects.filter(dni_ruc=user.dni_ruc).first()

    pedidos = Pedido.objects.none()
    equipos = EquipoRegistrado.objects.none()
    if cliente:
        pedidos = Pedido.objects.filter(cliente=cliente).prefetch_related('detalles').order_by('-fecha_pedido')[:50]
        equipos = EquipoRegistrado.objects.filter(cliente=cliente).select_related('producto')

    return render(
        request,
        'usuarios/mi_cuenta.html',
        {
            'cliente': cliente,
            'pedidos': pedidos,
            'equipos': equipos,
        },
    )
