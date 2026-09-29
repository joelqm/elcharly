from django.db import migrations, models


def seed_correlativos(apps, schema_editor):
    import re
    CorrelativoSerie = apps.get_model('pos', 'CorrelativoSerie')
    TicketPOS = apps.get_model('pos', 'TicketPOS')
    Pedido = apps.get_model('pedidos', 'Pedido')
    pat = re.compile(r'^([A-Z0-9]{4})-(\d{1,8})$', re.I)

    max_por_serie = {}
    for raw in list(TicketPOS.objects.values_list('numero_serie', flat=True)) + list(
        Pedido.objects.values_list('numero_pedido', flat=True)
    ):
        if not raw:
            continue
        m = pat.match(str(raw).strip())
        if not m:
            continue
        serie = m.group(1).upper()
        n = int(m.group(2))
        max_por_serie[serie] = max(max_por_serie.get(serie, 0), n)

    for serie in ('R001', 'B001', 'F001'):
        CorrelativoSerie.objects.update_or_create(
            serie=serie,
            defaults={'ultimo': max_por_serie.get(serie, 0)},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0005_alter_movimientocaja_metodo_pago'),
        ('pedidos', '0005_detalle_snapshot_venta'),
    ]

    operations = [
        migrations.CreateModel(
            name='CorrelativoSerie',
            fields=[
                ('serie', models.CharField(max_length=4, primary_key=True, serialize=False, verbose_name='Serie')),
                ('ultimo', models.PositiveIntegerField(default=0, verbose_name='Último correlativo')),
                ('actualizado', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Correlativo de serie',
                'verbose_name_plural': 'Correlativos de serie',
            },
        ),
        migrations.RunPython(seed_correlativos, migrations.RunPython.noop),
    ]
