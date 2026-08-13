from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0005_detalle_snapshot_venta'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pedido',
            name='fecha_pedido',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Fecha de Pedido'),
        ),
        migrations.AddField(
            model_name='pedido',
            name='es_historica',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='Cargada desde el cuaderno: no descuenta stock ni entra a la caja abierta.',
                verbose_name='Venta histórica',
            ),
        ),
    ]
