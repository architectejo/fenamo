"""Vérifie la cohérence entre l'état unique des membres et leurs booléens miroirs (§ 4.4)."""
from django.core.management.base import BaseCommand

from coptapp.services.verification_etats import LOT_AFFICHAGE, verifier


class Command(BaseCommand):
    help = ("Compte les membres par état, signale les écarts entre etat et miroirs (is_delete, is_validate2, is_validate3, renvoye) "
            "et liste les cas ambigus (id et idf seulement). --corriger resynchronise les miroirs depuis etat, rien d'autre.")

    def add_arguments(self, parser):
        parser.add_argument('--corriger', action='store_true', help='Recalculer les miroirs depuis etat.')
        parser.add_argument('--dry-run', action='store_true', help="N'écrire rien : avec --corriger, affiche seulement le plan.")

    def handle(self, *args, **options):
        r = verifier(corriger=options['corriger'], dry_run=options['dry_run'])
        out = self.stdout.write
        out(f"Membres lus : {r['total']}")
        for etat, n in r['par_etat'].items():
            out(f'  {etat} : {n}')
        if r['inconnus']:
            out(self.style.ERROR(f"État inconnu : {len(r['inconnus'])} membre(s)"))
            for pk, idf in r['inconnus'][:LOT_AFFICHAGE]:
                out(f'  id={pk} idf={idf}')
        out(f"Écarts état/miroirs : {len(r['ecarts'])}")
        for pk, idf, champs in r['ecarts'][:LOT_AFFICHAGE]:
            out(f"  id={pk} idf={idf} : {', '.join(champs)}")
        if len(r['ecarts']) > LOT_AFFICHAGE:
            out(f"  … et {len(r['ecarts']) - LOT_AFFICHAGE} autre(s)")
        out(f"Cas ambigus (à confirmer par l'utilisateur, jamais corrigés d'office) : {len(r['ambigus'])}")
        for pk, idf, raisons in r['ambigus'][:LOT_AFFICHAGE]:
            out(f"  id={pk} idf={idf} : {' ; '.join(raisons)}")
        if len(r['ambigus']) > LOT_AFFICHAGE:
            out(f"  … et {len(r['ambigus']) - LOT_AFFICHAGE} autre(s)")
        if options['corriger']:
            if options['dry_run']:
                out(f"Simulation : {len(r['ecarts'])} membre(s) seraient resynchronisés.")
            else:
                out(self.style.SUCCESS(f"{r['corriges']} membre(s) resynchronisé(s). Les cas ambigus restent à confirmer."))
