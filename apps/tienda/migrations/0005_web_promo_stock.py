# Generated manually: web promo prices + stock_web

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tienda', '0004_mostrar_en_web_precio_amplio'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='precio_tachado',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Precio anterior mostrado tachado. Si se llena junto al precio web, se marca como promoción.',
                max_digits=12,
                null=True,
                verbose_name='Precio tachado (web)',
            ),
        ),
        migrations.AddField(
            model_name='producto',
            name='precio_web',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Precio de venta en la tienda web. Si está vacío se usa el precio de lista.',
                max_digits=12,
                null=True,
                verbose_name='Precio final (web)',
            ),
        ),
        migrations.AddField(
            model_name='producto',
            name='stock_web',
            field=models.IntegerField(
                default=0,
                help_text='Unidades asignadas / disponibles para la tienda online.',
                verbose_name='Stock en web',
            ),
        ),
        migrations.AlterField(
            model_name='producto',
            name='stock',
            field=models.IntegerField(
                default=0,
                help_text='Unidades disponibles para venta presencial.',
                verbose_name='Stock en tienda (POS)',
            ),
        ),
    ]
