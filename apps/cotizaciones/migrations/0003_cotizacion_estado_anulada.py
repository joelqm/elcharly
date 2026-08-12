from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cotizaciones', '0002_cotizacion_sta_campos'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cotizacion',
            name='estado',
            field=models.CharField(
                choices=[
                    ('borrador', 'Borrador'),
                    ('enviada', 'Enviada al Cliente'),
                    ('aprobada', 'Aprobada (Convertida)'),
                    ('rechazada', 'Rechazada'),
                    ('anulada', 'Anulada'),
                ],
                default='borrador',
                max_length=20,
                verbose_name='Estado',
            ),
        ),
    ]
