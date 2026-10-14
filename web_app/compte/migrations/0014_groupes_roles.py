"""Huit groupes Django miroirs des rôles (``role_SU`` … ``role_ED``), réversible.

Le groupe d'un compte suit sa nomination active (``compte.services.nominations.synchroniser_groupe``). Cette migration ne crée
que les groupes, vides ; aucune nomination n'est créée. Retour arrière : les huit groupes sont supprimés (les comptes n'en gardent rien).
"""
from django.db import migrations

ROLES = ('SU', 'PR', 'VN', 'VP', 'VA', 'AT', 'VI', 'ED')


def creer_groupes(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for role in ROLES:
        Group.objects.get_or_create(name=f'role_{role}')


def supprimer_groupes(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name__in=[f'role_{r}' for r in ROLES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('compte', '0013_nomination'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(creer_groupes, supprimer_groupes),
    ]
