# Generated manually for destino field on MovimientoInventario

from django.db import migrations, models


def backfill_destino(apps, schema_editor):
    Movimiento = apps.get_model('inventario', 'MovimientoInventario')
    MotivosWeb = ('venta_web', 'reserva_web', 'liberacion_web')
    Movimiento.objects.filter(motivo__in=MotivosWeb).update(destino='web')


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0002_sedes_reserva_validacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimientoinventario',
            name='destino',
            field=models.CharField(
                choices=[('tienda', 'Stock tienda (POS)'), ('web', 'Stock web')],
                db_index=True,
                default='tienda',
                help_text='Indica si el movimiento afecta stock tienda o stock web.',
                max_length=10,
                verbose_name='Destino de stock',
            ),
        ),
        migrations.RunPython(backfill_destino, migrations.RunPython.noop),
    ]
