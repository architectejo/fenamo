"""Données FICTIVES de démonstration (jamais de données réelles) : comptes de chaque rôle, coordinations, antennes, associations
membres, membres à tous les états du circuit, engins numérotés, notifications, journal.

    python manage.py charger_donnees_demo                      (idempotente : ne refait rien si la démo est déjà chargée)
    python manage.py charger_donnees_demo --reinitialiser      (supprime UNIQUEMENT les objets de la démo, puis les recrée)
    python manage.py charger_donnees_demo --mot-de-passe XXXX  (mot de passe de tous les comptes de démo)

Les objets de démo sont reconnus à leur marqueur : comptes ``demo.*``, membres dont l'idf commence par ``DEMO``, antennes et
associations dont le code ou le numéro commence par ``DEMO``, engins dont le châssis commence par ``DEMO``, notifications ``[DEMO]``.
Tout passe par les vrais services (nomination, validation, suppression, numérotation F-31), donc le journal est réel.
Refuse de tourner hors DEBUG : pas de démonstration en production.
"""
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import PermissionDenied
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from compte import roles
from compte.models import JournalAction, Nomination
from compte.services import nominations as noms
from coptapp.models import Antenne, AssociationMembre, Membre, Moto, Notification, Province
from coptapp.services.actions import EtatIncoherent, renvoyer_membre, traiter_suppression_membre, valider_membre
from coptapp.services.engins import enregistrer_engin

PREFIXE = 'DEMO'
MOT_DE_PASSE_DEFAUT = 'Demo-Fenamo-2026'
IDF_MOBILE = 'DEMO-MOB'

PRENOMS = ['Jean-Pierre', 'Patrick', 'Joseph', 'Didier', 'Emmanuel', 'Christian', 'Papy', 'Fiston', 'Trésor', 'Blaise', 'Serge',
           'Dieudonné', 'Héritier', 'Gloire', 'Jonathan', 'Alain', 'Freddy', 'Mireille', 'Espérance', 'Bienvenu']
NOMS = ['Kabongo', 'Mukendi', 'Ilunga', 'Tshibangu', 'Kasongo', 'Mbuyi', 'Ngoy', 'Kalala', 'Mutombo', 'Banza', 'Lumbala', 'Kapend',
        'Nsimba', 'Makiese', 'Mbemba', 'Bolamba', 'Lokonda', 'Wetshi', 'Mapendo', 'Safari', 'Bahati', 'Kambale', 'Muhindo', 'Kitenge']
ASSOCIATIONS = [('Association des Motocyclistes Unis', 'AMU'), ('Taximen de la Paix', 'TAP'), ('Solidarité des Motards', 'SOLMO'),
                ('Union des Conducteurs de Moto', 'UCM'), ('Motards du Progrès', 'MOPRO'), ('Fraternité des Taximen', 'FRATAX')]
ANTENNES = [('Commune de la Gombe', 'commune'), ('Commune de Limete', 'commune'), ('Commune de Lubumbashi', 'commune'),
            ('Territoire de Kipushi', 'territoire'), ('Commune de Goma', 'commune'), ('Territoire de Nyiragongo', 'territoire')]
CODES_COORDINATIONS_PREFERES = ('Kinshasa', 'Haut-Katanga', 'Nord-Kivu')
MARQUES = [('TVS', 'Rouge'), ('Bajaj Boxer', 'Noire'), ('Haojue', 'Bleue'), ('Yamaha', 'Noire'), ('Honda', 'Rouge')]


class Command(BaseCommand):
    help = "Charge des données FICTIVES de démonstration (réservé au mode DEBUG)."

    def add_arguments(self, parser):
        parser.add_argument('--reinitialiser', action='store_true', help="Supprime les seuls objets de démo puis les recrée.")
        parser.add_argument('--mot-de-passe', default=MOT_DE_PASSE_DEFAUT, help="Mot de passe des comptes de démo (défaut : %(default)s).")

    # ------------------------------------------------------------------ point d'entrée
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Refus : les données de démonstration ne se chargent qu'avec DEBUG=True (jamais en production).")
        self.mdp = options['mot_de_passe']
        if len(self.mdp) < 8:
            raise CommandError("Le mot de passe de démo doit faire au moins 8 caractères.")
        Compte = get_user_model()
        if options['reinitialiser']:
            with transaction.atomic():
                self._supprimer_demo()
            self.stdout.write("Objets de démo supprimés.")
        elif Compte.objects.filter(username='demo.su').exists():
            self.stdout.write(self.style.WARNING(
                "La démo est déjà chargée : rien n'a été modifié. Pour repartir de zéro : --reinitialiser (le mot de passe reste celui "
                "défini au chargement)."))
            return
        with transaction.atomic():
            self._charger()
        self._afficher()

    # ------------------------------------------------------------------ suppression ciblée
    def _supprimer_demo(self):
        Compte = get_user_model()
        comptes = Compte.objects.filter(username__startswith='demo.')
        membres = Membre.objects.filter(idf__startswith=PREFIXE)
        Notification.objects.filter(Q(titre__startswith='[DEMO]') | Q(membre__idf__startswith=PREFIXE) | Q(user__in=comptes)).delete()
        Moto.objects.filter(num_chassie__startswith=PREFIXE).delete()
        JournalAction.objects.filter(auteur__in=comptes).delete()
        Nomination.objects.filter(compte__in=comptes).delete()
        comptes.delete()
        membres.delete()
        AssociationMembre.objects.filter(num_justice__startswith=PREFIXE).delete()
        Antenne.objects.filter(code__startswith=PREFIXE).delete()

    # ------------------------------------------------------------------ chargement
    def _essayer(self, libelle, fonction, *args, **kwargs):
        """Appelle un service ; un refus métier est affiché (jamais avalé en silence) et la démo continue."""
        try:
            return fonction(*args, **kwargs)
        except (PermissionDenied, EtatIncoherent, noms.ErreurNomination) as erreur:
            self.stdout.write(self.style.WARNING(f"  {libelle} : refusé ({erreur or type(erreur).__name__})"))
            return None

    def _charger(self):
        Compte = get_user_model()
        self.su = Compte.objects.create_superuser('demo.su', 'demo.su@example.invalid', self.mdp, first_name='Démo', last_name='Super-utilisateur')
        self.comptes = {'SU': self.su}
        self.coordinations = self._coordinations()
        self.antennes = self._antennes()
        self.associations = self._associations()
        a1 = self.antennes[0]
        # Membres porteurs de rôles (actifs), puis nominations par le vrai service.
        porteurs = [('PR', 'Mwamba', 'Président'), ('VN', 'Tshisekedi-Demo', 'Validateur national'), ('VP', 'Kanyinda', 'Validateur provincial'),
                    ('VA', 'Ndombe', "Validateur d'antenne"), ('AT', 'Mpoyi', 'Agent de terrain')]
        for code, nom, _libelle in porteurs:
            membre = self._membre(f'{nom} Démo', a1, 0, idf=f'{PREFIXE}-{code}')
            self._activer(membre)
            compte = Compte.objects.create_user(f'demo.{code.lower()}', f'demo.{code.lower()}@example.invalid', self.mdp,
                                                 membreId=membre.id, first_name=nom, last_name='Démo')
            perimetre = {'VP': {'coordination': self.coordinations[0]}, 'VA': {'antenne': a1}, 'AT': {'antenne': a1}}.get(code, {})
            noms.nommer(self.su, membre, getattr(roles, code), **perimetre)
            self.comptes[code] = Compte.objects.get(pk=compte.pk)
        for code, role in (('VI', roles.VI), ('ED', roles.ED)):
            compte, _n, _mdp = noms.creer_compte_externe(self.su, f'demo.{code.lower()}', role, email=f'demo.{code.lower()}@example.invalid')
            compte.set_password(self.mdp)
            compte.doit_changer_mot_de_passe = False
            compte.save(update_fields=['password', 'doit_changer_mot_de_passe'])
            self.comptes[code] = compte
        # Les comptes nommés ne doivent pas être forcés à changer leur mot de passe pendant la démo.
        Compte.objects.filter(username__startswith='demo.').update(doit_changer_mot_de_passe=False)
        self._membres()
        self._engins()
        self._notifications()

    def _coordinations(self):
        choisies = []
        for fragment in CODES_COORDINATIONS_PREFERES:
            province = Province.objects.filter(nom__icontains=fragment, code__isnull=False).order_by('ordre').first()
            if province and province not in choisies:
                choisies.append(province)
        for province in Province.objects.filter(code__isnull=False).order_by('ordre'):
            if len(choisies) >= 3:
                break
            if province not in choisies:
                choisies.append(province)
        if len(choisies) < 3:
            raise CommandError("Les 27 coordinations provinciales ne sont pas préchargées : lancez d'abord « python manage.py migrate ».")
        return choisies[:3]

    def _antennes(self):
        antennes = []
        for i, (nom, type_) in enumerate(ANTENNES):
            coordination = self.coordinations[i // 2]
            antennes.append(Antenne.objects.create(coordination=coordination, nom=nom, type=type_, code=f'{PREFIXE}-{coordination.code}-{i % 2 + 1}'))
        return antennes

    def _associations(self):
        associations = []
        for i, (nom, sigle) in enumerate(ASSOCIATIONS):
            antenne = self.antennes[i]
            associations.append(AssociationMembre.objects.create(
                nom=nom, sigle=sigle, antenne=antenne, province=antenne.coordination, num_justice=f'{PREFIXE}-J-{i + 1:03d}',
                nom_responsable=f'{PRENOMS[i]} {NOMS[i]}', phone=f'+243 81 000 00{i + 1:02d}', email=f'{sigle.lower()}@example.invalid'))
        return associations

    # ------------------------------------------------------------------ membres et circuit
    def _membre(self, nom, antenne, index, idf=None, saisi_par=None):
        association = next((a for a in self.associations if a.antenne_id == antenne.id), None)
        return Membre.objects.create(
            idf=idf or f'{PREFIXE}-{index:04d}', nom=nom[:50], genre='F' if nom.split()[0] in ('Mireille', 'Espérance') else 'M',
            date_naissance=date(1975 + index % 25, 1 + index % 12, 1 + index % 27), lieux_naissance='Kinshasa',
            telephone=f'+243 99 000 {index:04d}', mail=f'membre{index}@example.invalid', permis='A', categorie='Motard',
            province=antenne.coordination, antenne=antenne, structure=association, user=saisi_par, is_validate1=True)

    def _forcer(self, membre, **etat):
        for champ, valeur in etat.items():
            setattr(membre, champ, valeur)
        membre.save(update_fields=list(etat) + ['mise_a_jour'])

    def _activer(self, membre):
        """Valide tous les niveaux par le super-utilisateur (service réel) ; repli direct si le service ne le permet pas."""
        self._essayer(f'validation de {membre.nom}', valider_membre, self.su, membre)
        membre.refresh_from_db()
        if not (membre.is_validate2 and membre.is_validate3):
            self._forcer(membre, is_validate2=True, is_validate3=True)

    def _valider_par(self, auteur, membre, niveaux, repli):
        for _ in range(niveaux):
            self._essayer(f'validation de {membre.nom}', valider_membre, auteur, membre)
            membre.refresh_from_db()
        if (membre.is_validate2, membre.is_validate3) != repli:
            self._forcer(membre, is_validate2=repli[0], is_validate3=repli[1])

    def _noms(self, n):
        return [f'{PRENOMS[(i * 7) % len(PRENOMS)]} {NOMS[(i * 5 + 3) % len(NOMS)]}' for i in range(n)]

    def _membres(self):
        agent, va, vn = self.comptes['AT'], self.comptes['VA'], self.comptes['VN']
        noms_ = self._noms(40)
        self.membres = []
        a1 = self.antennes[0]
        for j in range(24):  # antenne principale : tous les états du circuit
            m = self._membre(noms_[j], a1, j + 1, saisi_par=agent)
            self.membres.append(m)
            if 6 <= j <= 11:
                self._valider_par(va, m, 1, (True, False))
            elif 12 <= j <= 23:
                self._valider_par(va, m, 1, (True, False))
                if j not in (21, 22):  # ces deux-là seront renvoyés par le validateur national
                    self._valider_par(vn, m, 1, (True, True))
        actifs_a1 = self.membres[12:24]
        for m in actifs_a1[6:8]:  # suppression demandée
            self._essayer(f'demande de suppression de {m.nom}', traiter_suppression_membre, va, m, 'demander', 'Fiche en double (démo)')
        m = actifs_a1[8]  # supprimé (demande puis exécution par le SU)
        self._essayer(f'demande de suppression de {m.nom}', traiter_suppression_membre, va, m, 'demander', 'Membre décédé (démo)')
        self._essayer(f'suppression de {m.nom}', traiter_suppression_membre, self.su, m, 'executer', 'Membre décédé (démo)')
        for m in actifs_a1[9:11]:  # renvoyés à l'auteur de la saisie par le validateur national, avec motif (service F-23)
            self._essayer(f'renvoi de {m.nom}', renvoyer_membre, vn, m, 'Photo illisible : à reprendre (démo)')
        self.mobile = actifs_a1[11]
        Membre.objects.filter(pk=self.mobile.pk).update(idf=IDF_MOBILE, password=make_password(self.mdp))
        self.mobile.refresh_from_db()
        for k in range(16):  # autres antennes
            antenne = self.antennes[1 + k % 5]
            m = self._membre(noms_[24 + k], antenne, 25 + k, saisi_par=agent)
            self.membres.append(m)
            if k >= 6:
                self._activer(m)

    def _engins(self):
        agent = self.comptes['AT']
        candidats = [m for m in self.membres if m.is_validate3 and not m.is_delete][:10]
        for i, membre in enumerate(candidats):
            marque, couleur = MARQUES[i % len(MARQUES)]
            self._essayer(f'engin de {membre.nom}', enregistrer_engin, membre, agent, {
                'num_plaque': f'{i + 1:04d}AB01', 'num_moteur': f'{PREFIXE}-MO-{i + 1:05d}', 'num_chassie': f'{PREFIXE}-CH-{i + 1:05d}',
                'marque': marque, 'couleur': couleur})

    def _notifications(self):
        textes = [('PR', 'Mandats à surveiller', "Trois mandats arrivent à échéance dans les 60 jours (données fictives)."),
                  ('VA', 'Fiches à valider', "Six fiches saisies attendent votre validation (données fictives)."),
                  ('AT', 'Fiche renvoyée', "Une fiche a été renvoyée : photo à reprendre (données fictives).")]
        for code, titre, description in textes:
            Notification.objects.create(user=self.comptes[code], titre=f'[DEMO] {titre}', description=description)

    # ------------------------------------------------------------------ résumé
    def _afficher(self):
        w = self.stdout.write
        w('')
        w(self.style.SUCCESS('Données de démonstration chargées (FICTIVES).'))
        w(f'{"Identifiant":<14}{"Rôle":<28}Mot de passe')
        for code in ('SU', 'PR', 'VN', 'VP', 'VA', 'AT', 'VI', 'ED'):
            w(f'{self.comptes[code].username:<14}{roles.LIBELLES[code]:<28}{self.mdp}')
        w(f'{IDF_MOBILE:<14}{"Membre (espace /mob/)":<28}{self.mdp}')
        w(f'Coordinations : {", ".join(c.nom for c in self.coordinations)} ; {len(self.antennes)} antennes ; '
          f'{len(self.associations)} associations membres ; {len(self.membres)} membres ; {Moto.objects.filter(num_chassie__startswith=PREFIXE).count()} engins.')
