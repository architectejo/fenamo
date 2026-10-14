"""Nomination SU du seul compte désigné ; affiche l'état des autres comptes sans rien leur attribuer (sous-lot 2e).

Exemple : python manage.py attribuer_roles_initiaux --su prestataire --dry-run
Le compte désigné doit déjà être super-utilisateur actif. AUCUNE autre nomination n'est créée : les présidents et les autres rôles
sont nommés ensuite par l'application (F-02). Rejouable : un compte qui a déjà sa nomination est laissé tel quel.
"""
from django.core.management.base import BaseCommand, CommandError

from compte.services.nominations import ErreurNomination, attribuer_nomination_su, etat_des_comptes


class Command(BaseCommand):
    help = "Crée la nomination SU du compte désigné et affiche l'état des autres comptes (sans leur attribuer de rôle)."

    def add_arguments(self, parser):
        parser.add_argument('--su', required=True, help="Nom d'utilisateur du super-utilisateur à nommer.")
        parser.add_argument('--dry-run', action='store_true', help='Ne rien créer : afficher ce qui serait fait.')

    def handle(self, *args, **options):
        try:
            compte, nomination, cree = attribuer_nomination_su(options['su'], dry_run=options['dry_run'])
        except ErreurNomination as erreur:
            raise CommandError(str(erreur))
        prefixe = 'Simulation : ' if options['dry_run'] else ''
        if nomination is not None and not cree:
            self.stdout.write(f"{prefixe}{compte.username} a déjà une nomination active ({nomination.role}) : rien à faire.")
        elif options['dry_run']:
            self.stdout.write(f"{prefixe}nomination SU de {compte.username} à créer.")
        else:
            self.stdout.write(f"Nomination SU créée pour {compte.username}.")
        autres = [(c, r) for c, r in etat_des_comptes() if c.pk != compte.pk or not (nomination or cree)]
        autres = [(c, r) for c, r in autres if c.pk != compte.pk]
        self.stdout.write(f"\n{len(autres)} autre(s) compte(s) sans nomination active (aucun rôle ne leur est attribué) :")
        for autre, resume in autres:
            self.stdout.write(f"  - {autre.username} : {resume}")
