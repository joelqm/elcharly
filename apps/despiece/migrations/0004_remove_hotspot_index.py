from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('despiece', '0003_despieceequipo_pdf'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='despiecehotspot',
            name='despiece_de_despiec_7a0c1d_idx',
        ),
    ]
