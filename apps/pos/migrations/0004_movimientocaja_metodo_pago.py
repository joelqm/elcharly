from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0003_precios_igv_caja_movimientos'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimientocaja',
            name='metodo_pago',
            field=models.CharField(
                default='efectivo',
                help_text='Solo el efectivo afecta el arqueo de gaveta.',
                max_length=20,
                verbose_name='Método de pago',
            ),
        ),
    ]
