"""Définit un mot de passe temporaire pour l'espace mobile (/mob/) d'un membre. Affiché UNE seule fois, jamais journalisé.

Exemple : python manage.py definir_mot_de_passe_membre MBR0000012 --auteur nom_du_super_utilisateur
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.management.base import BaseCommand, CommandError

from compte.services.mobile import definir_mot_de_passe_membre
from coptapp.models import Membre


class Command(BaseCommand):
    help = "Génère et enregistre (haché) un mot de passe temporaire pour l'espace mobile d'un membre."

    def add_arguments(self, parser):
        parser.add_argument('identifiant', help='Identifiant mobile du membre (MBR0000012).')
        parser.add_argument('--auteur', required=True, help="Nom d'utilisateur de qui agit (inscrit au journal).")

    def handle(self, *args, **options):
        auteur = get_user_model().objects.filter(username=options['auteur'], is_active=True).first()
        if auteur is None:
            raise CommandError('Auteur inconnu ou inactif.')
        membre = Membre.objects.filter(idf=options['identifiant'], is_delete=False).first()
        if membre is None:
            raise CommandError('Membre inconnu.')
        try:
            clair = definir_mot_de_passe_membre(auteur, membre)
        except PermissionDenied:
            raise CommandError("Cet auteur n'a pas le droit de définir le mot de passe de ce membre.")
        self.stdout.write(f"Mot de passe temporaire (à communiquer au membre, affiché une seule fois) : {clair}")
