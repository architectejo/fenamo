from django.db import migrations


class Migration(migrations.Migration):
    """Structure devient AssociationMembre (sans perte : renommage de table).

    Les champs `structure`, `type_de_structure` et le `related_name` restent
    inchangés tant que `mobapp` lit la base.
    """

    dependencies = [
        ('coptapp', '0046_membre_idf_membre_password'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Structure',
            new_name='AssociationMembre',
        ),
        migrations.AlterModelOptions(
            name='associationmembre',
            options={'verbose_name': 'association membre', 'verbose_name_plural': 'associations membres'},
        ),
        migrations.AlterModelOptions(
            name='moto',
            options={'verbose_name': 'engin', 'verbose_name_plural': 'engins'},
        ),
        migrations.AlterModelOptions(
            name='province',
            options={'verbose_name': 'coordination provinciale', 'verbose_name_plural': 'coordinations provinciales'},
        ),
    ]
