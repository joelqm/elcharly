from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cotizaciones', '0006_cotizacion_token_publico'),
    ]

    operations = [
        migrations.AddField(
            model_name='detallecotizacion',
            name='observacion',
            field=models.CharField(
                blank=True,
                default='',
                max_length=300,
                verbose_name='Observación / detalle',
            ),
        ),
    ]
