from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cotizaciones', '0004_alter_cotizacion_modelo_equipo_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cotizacion',
            name='observaciones',
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name='Observaciones / notas importantes (PDF)',
            ),
        ),
        migrations.AlterField(
            model_name='cotizacion',
            name='notas',
            field=models.TextField(blank=True, null=True, verbose_name='Notas internas'),
        ),
    ]
