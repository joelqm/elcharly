# Generated manually for background import + sale lock

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tienda', '0002_importacion_catalogo_makita'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='venta_bloqueada',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='Se activa durante importaciones de catálogo que afectan este producto.',
                verbose_name='Venta bloqueada',
            ),
        ),
        migrations.AddField(
            model_name='importacioncatalogo',
            name='archivo',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='importaciones/%Y/%m/',
                verbose_name='Archivo guardado',
            ),
        ),
        migrations.AddField(
            model_name='importacioncatalogo',
            name='estado',
            field=models.CharField(
                choices=[
                    ('pendiente', 'Pendiente'),
                    ('procesando', 'Procesando'),
                    ('completada', 'Completada'),
                    ('error', 'Error'),
                ],
                db_index=True,
                default='pendiente',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='importacioncatalogo',
            name='fecha_fin',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importacioncatalogo',
            name='mensaje_error',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='importacioncatalogo',
            name='total_procesadas',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
