from django.db import migrations, models


def poblar_nombre_busqueda(apps, schema_editor):
    from apps.tienda.search import normalizar_texto_busqueda

    Producto = apps.get_model('tienda', 'Producto')
    for p in Producto.objects.iterator():
        partes = [p.nombre or '', p.nombre_web or '', p.codigo_articulo or '', p.modelo or '']
        nb = normalizar_texto_busqueda(' '.join(x for x in partes if x))
        if p.nombre_busqueda != nb:
            Producto.objects.filter(pk=p.pk).update(nombre_busqueda=nb)


class Migration(migrations.Migration):

    dependencies = [
        ('tienda', '0013_alter_producto_tipo'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='nombre_busqueda',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='Sin tildes, minúsculas. Se actualiza al guardar.',
                max_length=512,
                verbose_name='Nombre normalizado (búsqueda)',
            ),
        ),
        migrations.RunPython(poblar_nombre_busqueda, migrations.RunPython.noop),
    ]
