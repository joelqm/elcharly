from django.db import migrations, models


def backfill_snapshots(apps, schema_editor):
    DetallePedido = apps.get_model('pedidos', 'DetallePedido')
    for d in DetallePedido.objects.select_related('producto').iterator(chunk_size=500):
        updates = []
        if not d.nombre_producto and d.producto_id:
            d.nombre_producto = (d.producto.nombre or '')[:255]
            updates.append('nombre_producto')
        if not d.codigo_articulo and d.producto_id:
            d.codigo_articulo = (d.producto.codigo_articulo or '')[:50]
            updates.append('codigo_articulo')
        if updates:
            d.save(update_fields=updates)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0004_sedes_reserva_validacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='detallepedido',
            name='codigo_articulo',
            field=models.CharField(
                blank=True,
                default='',
                max_length=50,
                verbose_name='Código al momento de la venta',
            ),
        ),
        migrations.AddField(
            model_name='detallepedido',
            name='nombre_producto',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Se congela al crear la línea. Un cambio de precio/nombre en el Excel no altera ventas antiguas.',
                max_length=255,
                verbose_name='Nombre al momento de la venta',
            ),
        ),
        migrations.RunPython(backfill_snapshots, noop_reverse),
    ]
