from decimal import Decimal

from django.db import migrations, models


def copiar_descuento_unico(apps, schema_editor):
    Ajuste = apps.get_model('pos', 'AjusteComercial')
    for obj in Ajuste.objects.all():
        pct = obj.descuento_lista_pct or Decimal('0')
        obj.descuento_repuestos_pct = pct
        obj.descuento_equipos_pct = pct
        obj.save(update_fields=['descuento_repuestos_pct', 'descuento_equipos_pct'])


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0007_ajustecomercial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ajustecomercial',
            name='descuento_repuestos_pct',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name='Descuento repuestos (%)',
            ),
        ),
        migrations.AddField(
            model_name='ajustecomercial',
            name='descuento_equipos_pct',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name='Descuento equipos y accesorios (%)',
            ),
        ),
        migrations.RunPython(copiar_descuento_unico, migrations.RunPython.noop),
    ]
