# Generated manually: web visibility + larger price field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tienda', '0003_venta_bloqueada_import_async'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='mostrar_en_web',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='Solo los productos marcados aquí aparecen en el catálogo público.',
                verbose_name='Mostrar en tienda web',
            ),
        ),
        migrations.AlterField(
            model_name='producto',
            name='activo',
            field=models.BooleanField(
                default=True,
                help_text='Si está activo puede usarse en POS e inventario interno.',
                verbose_name='Activo (POS / interno)',
            ),
        ),
        migrations.AlterField(
            model_name='producto',
            name='precio_venta',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=12,
                verbose_name='Precio de Venta (Lista General)',
            ),
        ),
        migrations.AlterField(
            model_name='producto',
            name='precio_costo',
            field=models.DecimalField(
                decimal_places=2,
                default=0.0,
                max_digits=12,
                verbose_name='Precio de Costo',
            ),
        ),
    ]
