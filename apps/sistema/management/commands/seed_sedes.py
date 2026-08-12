from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Crea empresa El Charly + sedes Tienda y Taller; asigna a staff.'

    def handle(self, *args, **options):
        from apps.sistema.models import Empresa, Sede
        from django.contrib.auth import get_user_model

        empresa, _ = Empresa.objects.get_or_create(
            ruc='10431549001',
            defaults={
                'nombre': 'STA El Charly Makita',
                'nombre_corto': 'El Charly',
            },
        )
        tienda, _ = Sede.objects.get_or_create(
            codigo='tienda',
            defaults={
                'empresa': empresa,
                'nombre': 'Tienda ASPYME',
                'tipo': Sede.TIPO_TIENDA,
                'direccion': 'Galería ASPYME, 2do Piso (Óvalo Mariscal Castilla), Arequipa',
                'whatsapp': '51960160842',
                'yape_numero': '960160842',
                'yape_titular': 'STA El Charly Makita',
                'compartir_productos': True,
                'orden': 1,
            },
        )
        taller, _ = Sede.objects.get_or_create(
            codigo='taller',
            defaults={
                'empresa': empresa,
                'nombre': 'Taller Divino Jesús',
                'tipo': Sede.TIPO_TALLER,
                'direccion': 'Pasaje Santa Catalina N° 100, Int. 16, Arequipa',
                'whatsapp': '51935829261',
                'compartir_productos': True,
                'orden': 2,
            },
        )
        User = get_user_model()
        for u in User.objects.filter(is_staff=True):
            u.sedes.add(tienda, taller)
            if not u.sede_activa_id:
                u.sede_activa = tienda
                u.save(update_fields=['sede_activa'])
        self.stdout.write(self.style.SUCCESS(
            f'Empresa #{empresa.id} · sedes {tienda.codigo}, {taller.codigo}'
        ))
