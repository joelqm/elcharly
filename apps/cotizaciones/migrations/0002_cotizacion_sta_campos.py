from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cotizaciones', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cotizacion',
            name='direccion_cliente_temporal',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Dirección (Manual)'),
        ),
        migrations.AddField(
            model_name='detallecotizacion',
            name='codigo_articulo',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='Código'),
        ),
        migrations.AddField(
            model_name='detallecotizacion',
            name='descripcion',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Descripción'),
        ),
        migrations.AddField(
            model_name='detallecotizacion',
            name='precio_costo',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=12,
                verbose_name='Precio compra / costo (interno)',
            ),
        ),
        migrations.AddField(
            model_name='detallecotizacion',
            name='precio_lista',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=12,
                verbose_name='Precio lista sin IGV (interno)',
            ),
        ),
        migrations.AlterField(
            model_name='detallecotizacion',
            name='precio_unitario',
            field=models.DecimalField(
                decimal_places=2, max_digits=10,
                verbose_name='Precio unitario (con IGV)',
            ),
        ),
    ]
