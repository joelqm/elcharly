# Generated manually for LogActividad

from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LogActividad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('login', 'Inicio de sesión'), ('logout', 'Cierre de sesión'), ('navegacion', 'Navegación'), ('venta', 'Venta / POS'), ('inventario', 'Inventario'), ('productos_web', 'Productos web'), ('importacion', 'Importación'), ('sistema', 'Sistema'), ('otro', 'Otro')], db_index=True, default='otro', max_length=30)),
                ('accion', models.CharField(max_length=120, verbose_name='Acción')),
                ('detalle', models.TextField(blank=True, default='')),
                ('ruta', models.CharField(blank=True, default='', max_length=255)),
                ('metodo', models.CharField(blank=True, default='', max_length=10)),
                ('ip', models.GenericIPAddressField(blank=True, null=True)),
                ('fecha', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='logs_actividad', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Log de actividad',
                'verbose_name_plural': 'Logs de actividad',
                'ordering': ['-fecha'],
            },
        ),
    ]
