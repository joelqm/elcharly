# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('despiece', '0002_paginas_hotspots'),
    ]

    operations = [
        migrations.AddField(
            model_name='despieceequipo',
            name='pdf',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='despieces/pdfs/',
                verbose_name='PDF original Makita',
            ),
        ),
    ]
