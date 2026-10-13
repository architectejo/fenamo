"""Hache les mots de passe de l'espace mobile (/mob/) encore enregistrés en clair (§ 9.1, sous-lot 2c).

Les valeurs déjà reconnues comme un hachage Django (``identify_hasher``) sont laissées telles quelles : la migration est
rejouable sans double hachage. ATTENTION : le hachage de chaque mot de passe prend une fraction de seconde (PBKDF2) ; pour
plusieurs milliers de membres, compter quelques minutes.

Fonction inverse : NE FAIT RIEN (``noop``). Un hachage ne se « dé-hache » pas ; revenir en arrière laisse les hachages en
place. L'ancien texte en clair n'est conservé nulle part : c'est voulu.
"""
from django.contrib.auth.hashers import identify_hasher, make_password
from django.db import migrations


def hacher(apps, schema_editor):
    Membre = apps.get_model('coptapp', 'Membre')
    for membre in Membre.objects.exclude(password__isnull=True).exclude(password='').iterator():
        try:
            identify_hasher(membre.password)
            continue  # déjà un hachage
        except ValueError:
            pass  # texte en clair : à hacher
        Membre.objects.filter(pk=membre.pk).update(password=make_password(membre.password))


class Migration(migrations.Migration):

    dependencies = [
        ('coptapp', '0054_membre_password_128'),
    ]

    operations = [
        migrations.RunPython(hacher, migrations.RunPython.noop),
    ]
