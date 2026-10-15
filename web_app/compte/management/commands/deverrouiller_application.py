"""Commande d'urgence : déverrouille l'application (F-07) quand plus aucun super-utilisateur ne peut se connecter.

    python manage.py deverrouiller_application --motif "Accès perdu, levée par le prestataire"

Journalisée sans auteur (DEVERROUILLAGE_APPLICATION). Code de retour 0 si l'application n'était pas verrouillée."""
from django.core.management.base import BaseCommand, CommandError

from compte.services.verrou_application import RegleVerrou, deverrouiller


class Command(BaseCommand):
    help = "Déverrouille l'application (commande d'urgence, journalisée sans auteur)."

    def add_arguments(self, parser):
        parser.add_argument('--motif', default='', help="Motif conservé au journal (500 caractères au plus).")

    def handle(self, *args, **options):
        try:
            leve = deverrouiller(None, options['motif'])
        except RegleVerrou as erreur:
            raise CommandError(str(erreur)) from erreur
        self.stdout.write(self.style.SUCCESS("Application déverrouillée.") if leve else "L'application n'était pas verrouillée : rien à faire.")
