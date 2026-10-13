"""Hache les mots de passe de l'espace mobile (/mob/) encore enregistrés en clair (§ 9.1, sous-lot 2c).

Les valeurs déjà reconnues comme un hachage Django (``identify_hasher``) sont laissées telles quelles : la migration est
rejouable sans double hachage, et reprenable après une interruption (``atomic = False`` : chaque membre est enregistré
au fur et à mesure, un arrêt au milieu ne perd pas le travail déjà fait).

DURÉE : le hachage par défaut (PBKDF2, environ un million d'itérations) prend une fraction de seconde par mot de passe ;
pour plusieurs milliers de membres, compter de quelques minutes à plusieurs heures. Lancer la migration hors des heures
d'usage et la relancer si elle est interrompue.

RETOUR ARRIÈRE : la fonction inverse NE FAIT RIEN (``noop``). Un hachage ne se « dé-hache » pas, et l'ancien texte en clair
n'est conservé nulle part (voulu). Revenir à une version antérieure du code qui comparait le texte en clair rendrait donc
IMPOSSIBLES les connexions /mob/ des membres concernés. Le retour arrière de 0054 (colonne ramenée à 100 caractères) n'est
pas sûr après cette migration : voir son avertissement.
"""
from django.contrib.auth.hashers import identify_hasher, make_password
from django.db import migrations


def hacher(apps, schema_editor):
    Membre = apps.get_model('coptapp', 'Membre')
    for membre in Membre.objects.exclude(password__isnull=True).exclude(password='').iterator():
        try:
            identify_hasher(membre.password)  # déjà un hachage : rien à faire
        except ValueError:
            Membre.objects.filter(pk=membre.pk).update(password=make_password(membre.password))  # texte en clair


class Migration(migrations.Migration):

    atomic = False  # un membre à la fois : reprise possible

    dependencies = [
        ('coptapp', '0054_membre_password_128'),
    ]

    operations = [
        migrations.RunPython(hacher, migrations.RunPython.noop),
    ]
