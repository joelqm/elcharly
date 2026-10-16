from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0006_correlativo_serie'),
    ]

    operations = [
        migrations.CreateModel(
            name='AjusteComercial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('descuento_lista_pct', models.DecimalField(
                    decimal_places=2,
                    default=0,
                    max_digits=5,
                    verbose_name='Descuento sobre lista con IGV (%)',
                )),
                ('actualizado', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Ajuste comercial',
                'verbose_name_plural': 'Ajuste comercial',
            },
        ),
    ]
