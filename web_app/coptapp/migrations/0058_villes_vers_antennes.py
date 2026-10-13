"""Chaque ancienne « ville » devient une antenne (le niveau ville disparaît, charte art. 66).

- Pour chaque Ville sans antenne issue : Antenne(nom, coordination = province de la ville, ville_origine = ville,
  type vide, code vide). Les cas ambigus (province absente, Kinshasa à répartir entre Est et Ouest) gardent la
  coordination telle quelle ; ils sont à examiner par l'utilisateur.
- Membre.antenne, Moto.antenne, AssociationMembre.antenne ne sont remplis que s'ils sont vides et si la ville est
  renseignée ; un rattachement existant n'est jamais remplacé.
- Rejouable. Retour arrière : remet à NULL TOUS les rattachements (Membre.antenne, Moto.antenne, AssociationMembre.antenne)
  qui pointent vers une antenne issue d'une ville, puis supprime ces antennes. Sa portée est donc plus large que l'aller :
  il efface aussi les rattachements faits À LA MAIN après la migration vers ces antennes (par l'application, par `mobapp`).
  Les membres gardent leur `ville` : seule l'information « antenne » est perdue. À éviter une fois l'application en usage.
"""
from django.db import migrations


def villes_vers_antennes(apps, schema_editor):
    Ville = apps.get_model('coptapp', 'Ville')
    Antenne = apps.get_model('coptapp', 'Antenne')
    for ville in Ville.objects.filter(antenne_issue__isnull=True).order_by('pk'):
        Antenne.objects.create(nom=ville.nom, coordination_id=ville.province_id, ville_origine=ville, type='', code=None)
    for nom_modele in ('Membre', 'Moto', 'AssociationMembre'):
        Modele = apps.get_model('coptapp', nom_modele)
        for antenne in Antenne.objects.filter(ville_origine__isnull=False).order_by('pk'):
            Modele.objects.filter(antenne__isnull=True, ville_id=antenne.ville_origine_id).update(antenne=antenne)


def antennes_vers_villes(apps, schema_editor):
    Antenne = apps.get_model('coptapp', 'Antenne')
    issues = Antenne.objects.filter(ville_origine__isnull=False)
    for nom_modele in ('Membre', 'Moto', 'AssociationMembre'):
        apps.get_model('coptapp', nom_modele).objects.filter(antenne__in=issues).update(antenne=None)
    issues.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('coptapp', '0057_precharger_coordinations'),
    ]

    operations = [
        migrations.RunPython(villes_vers_antennes, antennes_vers_villes),
    ]
