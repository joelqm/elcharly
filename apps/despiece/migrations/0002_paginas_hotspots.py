# Generated manually for pages + hotspots

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('despiece', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DespiecePagina',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero', models.PositiveSmallIntegerField(default=1, verbose_name='Nº de página')),
                ('imagen', models.ImageField(upload_to='despieces/diagramas/', verbose_name='Imagen de la página')),
                ('despiece', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='paginas', to='despiece.despieceequipo', verbose_name='Despiece')),
            ],
            options={
                'verbose_name': 'Página de despiece',
                'verbose_name_plural': 'Páginas de despiece',
                'ordering': ['numero'],
                'unique_together': {('despiece', 'numero')},
            },
        ),
        migrations.CreateModel(
            name='DespieceHotspot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pagina', models.PositiveSmallIntegerField(db_index=True, default=1, verbose_name='Página')),
                ('posicion', models.CharField(db_index=True, help_text='Debe coincidir con DespieceItem.posicion (ej. 88 o 016).', max_length=30, verbose_name='Posición (Art. No.)')),
                ('cx', models.FloatField(verbose_name='Centro X %')),
                ('cy', models.FloatField(verbose_name='Centro Y %')),
                ('r', models.FloatField(default=2.2, verbose_name='Radio % del ancho')),
                ('despiece', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hotspots', to='despiece.despieceequipo', verbose_name='Despiece')),
            ],
            options={
                'verbose_name': 'Hotspot de despiece',
                'verbose_name_plural': 'Hotspots de despiece',
                'ordering': ['pagina', 'posicion'],
            },
        ),
        migrations.AddIndex(
            model_name='despiecehotspot',
            index=models.Index(fields=['despiece', 'pagina', 'posicion'], name='despiece_de_despiec_7a0c1d_idx'),
        ),
    ]
