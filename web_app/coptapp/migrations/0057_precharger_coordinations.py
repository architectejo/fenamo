"""Précharge les 27 coordinations provinciales de la charte (art. 43, annexe C du cahier des charges).

Règles : ``get_or_create`` par code ; une province existante n'est jamais modifiée ; un code déjà présent n'est jamais
recréé ni changé ; aucune fusion automatique avec les provinces de l'ancien projet (la correspondance reste à décider
par l'utilisateur). Rejouable : un second passage ne crée rien.
"""
from django.db import migrations

# (ordre, nom, code) : annexe C, charte art. 43. Aucune donnée personnelle.
COORDINATIONS = [
    (1, 'Bas-Uele', 'BU'),
    (2, 'Équateur', 'EQ'),
    (3, 'Haut-Katanga', 'HK'),
    (4, 'Haut-Lomami', 'HL'),
    (5, 'Haut-Uele', 'HU'),
    (6, 'Ituri', 'IT'),
    (7, 'Kasaï', 'KA'),
    (8, 'Kasaï Central', 'KC'),
    (9, 'Kasaï Oriental', 'KO'),
    (10, 'Kinshasa-Est', 'KN-E'),
    (11, 'Kinshasa-Ouest', 'KN-O'),
    (12, 'Kongo-Central', 'KOC'),
    (13, 'Kwango', 'KW'),
    (14, 'Kwilu', 'KL'),
    (15, 'Lomami', 'LO'),
    (16, 'Lualaba', 'LW'),
    (17, 'Mai-Ndombe', 'MD'),
    (18, 'Maniema', 'MN'),
    (19, 'Mongala', 'MO'),
    (20, 'Nord-Ubangi', 'NU'),
    (21, 'Nord-Kivu', 'NK'),
    (22, 'Sankuru', 'SA'),
    (23, 'Sud-Kivu', 'SK'),
    (24, 'Sud-Ubangi', 'SU'),
    (25, 'Tanganyika', 'TG'),
    (26, 'Tshopo', 'TS'),
    (27, 'Tshuapa', 'TP'),
]


def precharger(apps, schema_editor):
    Province = apps.get_model('coptapp', 'Province')
    for ordre, nom, code in COORDINATIONS:
        Province.objects.get_or_create(code=code, defaults={'nom': nom, 'ordre': ordre})


def _est_referencee(apps, province):
    Province = apps.get_model('coptapp', 'Province')
    for relation in Province._meta.related_objects:
        if relation.related_model.objects.filter(**{relation.field.name: province}).exists():
            return True
    return False


def retirer(apps, schema_editor):
    """Supprime seulement les coordinations telles que créées par la migration (code, nom, ordre d'origine, sans sigle ni
    responsable) et qui ne sont référencées par rien. Les autres restent."""
    Province = apps.get_model('coptapp', 'Province')
    for ordre, nom, code in COORDINATIONS:
        province = Province.objects.filter(code=code, nom=nom, ordre=ordre, sigle=None, user=None).first()
        if province is not None and not _est_referencee(apps, province):
            province.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('coptapp', '0056_geographie_champs'),
    ]

    operations = [
        migrations.RunPython(precharger, retirer),
    ]
