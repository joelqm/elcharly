from django.apps import AppConfig

class UsuariosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.usuarios'

    def ready(self):
        # Parche para django-unfold para prevenir "ValueError: dictionary update sequence element #0 has length X; 2 is required"
        try:
            import unfold.templatetags.unfold as unfold_tags
            from typing import Any

            def safe_flatten_context(context) -> dict[str, Any]:
                keys = set()
                for d in context.dicts:
                    if hasattr(d, "keys"):
                        keys.update(d.keys())
                return {k: context[k] for k in keys}

            unfold_tags._flatten_context = safe_flatten_context
        except ImportError:
            pass
