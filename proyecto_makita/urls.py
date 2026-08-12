"""
URL configuration for proyecto_makita project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from proyecto_makita.views import health, robots_txt

urlpatterns = [
    path('robots.txt', robots_txt, name='robots_txt'),
    path('health/', health, name='health'),
    path('admin/', admin.site.urls),
    path('', include('apps.tienda.urls')),
    path('', include('apps.usuarios.urls')),
    path('', include('apps.pedidos.urls')),
    path('', include('apps.pagos.urls')),
    path('', include('apps.pos.urls')),
    path('', include('apps.mantenimiento.urls')),
    path('', include('apps.clientes.urls')),
    path('', include('apps.cotizaciones.urls')),
    path('', include('apps.reportes.urls')),
    path('', include('apps.despiece.urls')),
]

# Media: en DEBUG lo sirve Django; en prod simple también (mejor nginx/CDN luego).
urlpatterns += [
    path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

handler400 = 'proyecto_makita.views.bad_request'
handler403 = 'proyecto_makita.views.permission_denied'
handler404 = 'proyecto_makita.views.page_not_found'
handler500 = 'proyecto_makita.views.server_error'
