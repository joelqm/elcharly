from django.apps import AppConfig


class SistemaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sistema'
    verbose_name = 'Sistema'

    def ready(self):
        from django.contrib import admin
        from django.shortcuts import redirect
        from django.urls import path
        from . import views
        from apps.tienda import views_importacion as views_tienda

        # Signals login/logout (import late)
        try:
            from . import middleware  # noqa: F401
        except Exception:
            pass

        if getattr(admin.site, '_sistema_urls_patched', False):
            return

        original_get_urls = admin.site.get_urls
        original_index = admin.site.index

        def admin_index_redirect(request, extra_context=None):
            if request.GET.get('stay') == '1':
                return original_index(request, extra_context)
            return redirect('/pos/inicio/')

        def get_urls():
            custom = [
                path(
                    'sistema/respaldo/',
                    admin.site.admin_view(views.respaldo_view),
                    name='sistema_respaldo',
                ),
                path(
                    'sistema/respaldo/exportar/',
                    admin.site.admin_view(views.exportar_base_datos),
                    name='sistema_exportar',
                ),
                path(
                    'sistema/respaldo/importar/',
                    admin.site.admin_view(views.importar_base_datos),
                    name='sistema_importar',
                ),
                path(
                    'tienda/importar-catalogo/',
                    admin.site.admin_view(views_tienda.importar_catalogo_view),
                    name='tienda_importar_catalogo',
                ),
                path(
                    'tienda/importar-catalogo/upload/',
                    admin.site.admin_view(views_tienda.importar_catalogo_upload),
                    name='tienda_importar_catalogo_upload',
                ),
            ]
            return custom + original_get_urls()

        admin.site.get_urls = get_urls
        admin.site.index = admin_index_redirect
        admin.site._sistema_urls_patched = True
