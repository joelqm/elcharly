from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('despiece', '0004_remove_hotspot_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='despiecehotspot',
            name='puntos',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Polígono [{x, y}, …] en porcentaje del diagrama. Vacío = solo pin del número.',
                verbose_name='Silueta (puntos %)',
            ),
        ),
    ]
