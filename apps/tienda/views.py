from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Producto, Categoria
from .cart import Cart, CartStockError


def _qs_web():
    """Catálogo público: solo productos explícitamente publicados."""
    return (
        Producto.objects.filter(activo=True, mostrar_en_web=True)
        .exclude(tipo=Producto.TIPO_REPUESTO)
        .exclude(familia_sap__iexact='REPUESTOS')
    )


def _safe_next_url(request, candidate):
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return None


def home(request):
    """Landing tipo tienda: servicios + productos publicados en web."""
    destacados = _qs_web().order_by('-fecha_creacion')[:8]
    categorias = (
        Categoria.objects.filter(categoria_padre__isnull=True)
        .exclude(slug='repuestos')
        .exclude(nombre__iexact='Repuestos')[:6]
    )
    return render(
        request,
        'tienda/home.html',
        {
            'destacados': destacados,
            'categorias': categorias,
        },
    )


def catalogo_productos(request):
    productos = _qs_web()
    categorias = (
        Categoria.objects.all()
        .exclude(slug='repuestos')
        .exclude(nombre__iexact='Repuestos')
    )

    q = request.GET.get('q', '')
    if q:
        from apps.tienda.search import filtrar_productos
        productos = filtrar_productos(productos, q)

    categoria_slug = request.GET.get('categoria', '')
    categoria_seleccionada = None
    if categoria_slug:
        categoria_seleccionada = get_object_or_404(Categoria, slug=categoria_slug)
        categorias_ids = [categoria_seleccionada.id] + list(
            categoria_seleccionada.subcategorias.values_list('id', flat=True)
        )
        productos = productos.filter(categoria_id__in=categorias_ids)

    familia = request.GET.get('familia', '')
    if familia:
        productos = productos.filter(familia_sap=familia)

    min_precio = request.GET.get('min_precio', '')
    max_precio = request.GET.get('max_precio', '')
    if min_precio:
        try:
            productos = productos.filter(precio_venta__gte=float(min_precio))
        except ValueError:
            pass
    if max_precio:
        try:
            productos = productos.filter(precio_venta__lte=float(max_precio))
        except ValueError:
            pass

    voltaje = request.GET.get('voltaje', '')
    if voltaje:
        productos = productos.filter(voltaje=voltaje)

    orden = request.GET.get('orden', '')
    if orden == 'precio_asc':
        productos = productos.order_by('precio_venta')
    elif orden == 'precio_desc':
        productos = productos.order_by('-precio_venta')
    elif orden == 'recientes':
        productos = productos.order_by('-fecha_creacion')

    voltajes_disponibles = (
        _qs_web()
        .exclude(voltaje__isnull=True)
        .exclude(voltaje='')
        .values_list('voltaje', flat=True)
        .distinct()
    )
    familias_disponibles = (
        _qs_web()
        .values_list('familia_sap', flat=True)
        .distinct()
    )

    context = {
        'productos': productos,
        'categorias': categorias,
        'categoria_seleccionada': categoria_seleccionada,
        'voltajes_disponibles': voltajes_disponibles,
        'familias_disponibles': familias_disponibles,
        'filtros': {
            'q': q,
            'categoria': categoria_slug,
            'familia': familia,
            'min_precio': min_precio,
            'max_precio': max_precio,
            'voltaje': voltaje,
            'orden': orden,
        },
    }
    return render(request, 'tienda/catalogo.html', context)


def detalle_producto(request, slug):
    producto = get_object_or_404(
        Producto.objects.prefetch_related('atributos', 'imagenes'),
        slug=slug, activo=True, mostrar_en_web=True,
    )
    recomendados = _qs_web().filter(
        familia_sap=producto.familia_sap,
    ).exclude(id=producto.id)[:4]
    galeria = producto.imagenes_galeria()

    context = {
        'producto': producto,
        'recomendados': recomendados,
        'galeria': galeria,
        'atributos_ficha': (
            producto.atributos.all()
            if producto.mostrar_ficha_tecnica
            else []
        ),
    }
    return render(request, 'tienda/detalle.html', context)


@require_http_methods(["GET", "POST"])
def cart_add(request, producto_id):
    cart = Cart(request)
    producto = get_object_or_404(Producto, id=producto_id, activo=True, mostrar_en_web=True)

    cantidad = 1
    override = False
    next_url = _safe_next_url(
        request,
        request.POST.get('next') or request.GET.get('next') or '',
    )
    quiet = request.method == 'GET'  # +/- del carrito sin spam de mensajes

    if request.method == 'POST':
        try:
            cantidad = int(request.POST.get('cantidad', 1))
        except (TypeError, ValueError):
            cantidad = 1
        override = request.POST.get('override') == '1'
    else:
        try:
            cantidad = int(request.GET.get('cantidad', 1))
        except (TypeError, ValueError):
            cantidad = 1
        if request.GET.get('override') == '1' or 'set' in request.GET:
            override = True
            if 'set' in request.GET:
                try:
                    cantidad = int(request.GET.get('set'))
                except (TypeError, ValueError):
                    cantidad = 1
        else:
            producto_id_str = str(producto.id)
            actual = cart.cart.get(producto_id_str, {}).get('cantidad', 0)
            override = True
            cantidad = actual + cantidad

    try:
        cart.add(producto=producto, cantidad=cantidad, override_cantidad=override)
        if not quiet:
            messages.success(request, f'«{producto.nombre}» se agregó al carrito.')
    except CartStockError as e:
        messages.error(request, e.mensaje)

    if next_url:
        return redirect(next_url)
    return redirect('tienda:cart_detail')


def cart_remove(request, producto_id):
    cart = Cart(request)
    producto = get_object_or_404(Producto, id=producto_id)
    cart.remove(producto)
    messages.info(request, f'«{producto.nombre}» eliminado del carrito.')
    return redirect('tienda:cart_detail')


def cart_detail(request):
    cart = Cart(request)
    return render(request, 'tienda/cart_detail.html', {'cart': cart})
