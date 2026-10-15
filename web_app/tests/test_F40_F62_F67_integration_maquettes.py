"""Rendu des écrans intégrés d'après les maquettes : communiqués (F-40), données réelles (F-67, DR-01), messages de contact (F-62).

Teste le balisage (classes des maquettes, accessibilité, échappement, droits visibles) ; les règles métier ont leurs propres tests."""
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from compte import roles
from coptapp.services import communiques as S
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_F40_communiques import equipe  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401
from coptapp.models import Communique
from virtrine.models import Contact

pytestmark = pytest.mark.django_db
HX = {'HTTP_HX_REQUEST': 'true'}
INJECTION = '<script>alert(1)</script>'


def _html(reponse):
    return reponse.content.decode()


# ---------------------------------------------------------------- CSS

def test_F40_css_section_communication_reportee_et_anciennes_regles_retirees():
    css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    for regle in ('.portee {', '.communique-ligne {', '.lecture-texte', '.destinataires {', '.choix--cibles', '.ligne--a-traiter', '.apercu-ligne', '.coordonnees', '.traite-par',
                  '.haut .rangee--serree { gap: 0; }'):
        assert regle in css, regle
    for ancienne in ('.dossier.communique.non-lu', '.communique-icone', '.file--communiques', '.communique-cibles', '.communique-texte'):
        assert ancienne not in css, ancienne
    assert not re.search(r'\.communique[^{]*\{[^}]*animation', css)  # aucune animation d'apparition sur les lignes


# ---------------------------------------------------------------- barre haute et menu

def test_F40_badge_communiques_annonce_le_nombre_sans_aria_label_ecrasant(client, monde, equipe):
    client.force_login(equipe['VA_P'])
    page = _html(client.get(reverse('tableau-bord')))
    lien = re.search(r'<a class="bouton-icone" href="[^"]*communiques/[^"]*"[^>]*>.*?</a>', page, re.S).group(0)
    assert 'aria-label' not in lien.split('>')[0] and '<span class="lecteur">Communiqués</span>' in lien


def test_F40_menu_groupes_communication_et_site_public(client, monde, equipe, jeu):
    client.force_login(jeu['compte'])
    page = _html(client.get(reverse('tableau-bord')))
    assert 'Site public' in page and reverse('contact') in page
    client.force_login(equipe['VA_P'])
    assert reverse('contact') not in _html(client.get(reverse('tableau-bord')))  # réservé à SU et ED


# ---------------------------------------------------------------- communiqués : liste

def test_F40_liste_ligne_cliquable_portee_et_non_lu(client, monde, equipe):
    type(monde['P']).objects.filter(pk=monde['P'].pk).update(code='PX')
    S.publier(equipe['ED'], 'National A', 'Texte national')
    S.publier(equipe['ED'], 'Coordination B', 'Texte coordination', coordination=monde['P'])
    S.publier(equipe['ED'], 'Antenne C', 'Texte antenne', antenne=monde['antenne_p'])
    client.force_login(equipe['VA_P'])
    page = _html(client.get(reverse('list-message')))
    assert 'class="communique-ligne non-lu"' in page and 'communique-lien' in page and 'communique-nouveau' in page
    assert 'portee portee--national' in page and 'portee-code' in page and f'Antenne de {monde["antenne_p"].nom}' in page
    assert 'avatar' not in page.split('id="liste-zone"')[1].split('<nav class="pages"')[0]  # pas d'avatar dans les lignes
    assert 'Antenne Antenne' not in page


def test_F40_liste_filtres_coordination_et_antenne_pour_editeur_seulement(client, monde, equipe):
    S.publier(equipe['ED'], 'Un', 'texte')
    client.force_login(equipe['ED'])
    page = _html(client.get(reverse('list-message')))
    assert 'id="f-coordination"' in page and 'id="f-antenne"' in page and '<optgroup label=' in page and 'filtres-deplier' in page
    client.force_login(equipe['VA_P'])
    page = _html(client.get(reverse('list-message')))
    assert 'id="f-coordination"' not in page and 'type="hidden" name="coordination"' in page


def test_F40_liste_trois_etats_vides_et_resume(client, monde, equipe):
    Communique.objects.all().delete()
    client.force_login(equipe['ED'])
    vide = _html(client.get(reverse('list-message'), **HX))
    assert 'Aucun communiqué pour l&#x27;instant' in vide or "Aucun communiqué pour l'instant" in vide
    assert 'Publier un communiqué' in vide
    aucun = _html(client.get(reverse('list-message'), {'q': 'zzz'}, **HX))
    assert 'Aucun communiqué ne correspond' in aucun and 'Effacer les filtres' in aucun and 'zzz' in aucun
    lu = _html(client.get(reverse('list-message'), {'etat': 'non_lus'}, **HX))
    assert 'Tout est lu' in lu and 'Voir tous les communiqués' in lu
    S.publier(equipe['ED'], 'Un', 'texte')
    rempli = _html(client.get(reverse('list-message'), **HX))
    assert 'resume-liste' in rempli and '1 à 1 sur 1' in rempli and '<html' not in rempli


def test_F40_liste_echappe_le_contenu(client, monde, equipe):
    S.publier(equipe['ED'], INJECTION, INJECTION + ' suite')
    client.force_login(equipe['VA_P'])
    page = _html(client.get(reverse('list-message')))
    assert INJECTION not in page and '&lt;script&gt;' in page


# ---------------------------------------------------------------- communiqués : lecture et modale

def test_F40_lecture_mise_en_page_signature_et_texte_brut(client, monde, equipe):
    c = S.publier(equipe['ED'], 'Titre lu', 'Ligne 1\nLigne 2 ' + INJECTION)
    client.force_login(equipe['VA_P'])
    page = _html(client.get(reverse('communique', kwargs={'id': c.pk})))
    assert 'panneau lecture' in page and 'lecture-texte' in page and 'lecture-signature' in page and 'lecture-pied' in page
    assert 'panneau--etroit' not in page and '<br' not in page.split('lecture-texte')[1].split('</p>')[0]
    assert INJECTION not in page and '&lt;script&gt;' in page and 'Publié le' in page and 'Tous les communiqués' in page


def test_F40_modale_publier_ordre_cibles_et_listes(client, monde, equipe):
    client.force_login(equipe['ED'])
    modale = _html(client.get(reverse('message'), **HX))
    assert modale.index('Destinataires') < modale.index('class="destinataires"') < modale.index('for="c-titre"') < modale.index('for="c-message"')
    assert 'choix choix--cibles' in modale and 'class="coche"' in modale and 'communique-cibles' not in modale
    assert '<optgroup label=' in modale and 'c-antenne-filtre' not in modale  # une seule liste d'antennes
    assert 'Dites quoi, où, quand' in modale and 'Il arrive dans les notifications' in modale
    pied = modale.split('feuille-pied')[1]
    assert 'icons.svg#i-send' not in pied


def test_F40_modale_publier_erreurs_sous_les_champs(client, monde, equipe):
    client.force_login(equipe['ED'])
    r = client.post(reverse('message'), {'titre': '', 'message': 'texte', 'cible': 'antenne'}, **HX)
    html = _html(r)
    assert r.status_code == 422 and 'aria-invalid="true"' in html and 'champ-erreur' in html and 'texte' in html


# ---------------------------------------------------------------- messages de contact

def _message(**kw):
    donnees = {'nom': 'Jean Test', 'mail': 'jean@example.org', 'phone': '+243 997 214 508', 'raison': 'Adhésion', 'description': 'Bonjour\nSuite',
               'cree_le': timezone.now()}
    donnees.update(kw)
    return Contact.objects.create(**donnees)


def test_F62_contact_acces_su_et_ed_seulement(client, monde, equipe, jeu):
    for cle in ('VA_P', 'AT_P', 'PR', 'VI_NAT'):
        client.force_login(equipe[cle])
        assert client.get(reverse('contact')).status_code == 403, cle
    for compte in (jeu['compte'], equipe['ED']):
        client.force_login(compte)
        assert client.get(reverse('contact')).status_code == 200


def test_F62_contact_liste_colonnes_filtres_et_echappement(client, monde, equipe):
    message = _message(nom=INJECTION, raison=INJECTION, description=INJECTION)
    _message(nom='Traité', raison='Ancien', traiter=True)
    client.force_login(equipe['ED'])
    page = _html(client.get(reverse('contact')))
    for attendu in ('Objet', 'Expéditeur', 'Reçu le', 'ligne--a-traiter', 'apercu-ligne', 'data-role="etat"', 'resume-liste', 'name="etat"',
                    'Nom, téléphone, e-mail ou objet', reverse('contact-view', kwargs={'id': message.pk})):
        assert attendu in page, attendu
    assert 'Raison' not in page and INJECTION not in page and '&lt;script&gt;' in page
    assert 'Ancien' not in page  # « À traiter » par défaut
    assert 'Ancien' in _html(client.get(reverse('contact'), {'etat': 'tous'}))
    fragment = _html(client.get(reverse('contact'), {'etat': 'tous'}, **HX))
    assert '<html' not in fragment and 'ligne--traitee' in fragment


def test_F62_contact_liste_vide_et_sans_resultat(client, monde, equipe):
    Contact.objects.all().delete()
    client.force_login(equipe['ED'])
    assert 'Aucun message à traiter' in _html(client.get(reverse('contact')))
    _message()
    assert 'Aucun message ne correspond' in _html(client.get(reverse('contact'), {'q': 'zzz'}))


def test_F62_contact_detail_coordonnees_message_en_texte_saisi(client, monde, equipe):
    message = _message(description='<b>gras</b>\nSuite')
    client.force_login(equipe['ED'])
    page = _html(client.get(reverse('contact-view', kwargs={'id': message.pk})))
    assert 'message-su' in page and 'texte-saisi' in page and '&lt;b&gt;gras&lt;/b&gt;' in page and '<b>gras</b>' not in page
    assert 'href="tel:+243997214508"' in page and 'href="mailto:jean@example.org"' in page and 'Appeler' in page and 'Écrire un e-mail' in page
    assert "l&#x27;application n&#x27;envoie pas de réponse" in page or "l'application n'envoie pas de réponse" in page
    assert 'Marquer comme traité' in page and 'csrfmiddlewaretoken' in page and 'hx-post' in page and 'bouton--valider bouton--bloc-mobile' in page
    assert 'Messages reçus' in page and 'Adhésion' in page
    sans = _message(mail=None, phone=None)
    page = _html(client.get(reverse('contact-view', kwargs={'id': sans.pk})))
    assert "Pas d&#x27;adresse e-mail donnée." in page or "Pas d'adresse e-mail donnée." in page and 'mailto:' not in page


def test_F62_contact_detail_get_n_ecrit_rien_et_post_traite_avec_traite_par(client, monde, equipe):
    message = _message()
    client.force_login(equipe['ED'])
    url = reverse('contact-view', kwargs={'id': message.pk})
    client.get(url)
    message.refresh_from_db()
    assert not message.traiter
    r = client.post(url, **HX)
    html = _html(r)
    message.refresh_from_db()
    assert message.traiter and r.status_code == 200
    assert 'id="expediteur"' in html and 'traite-par' in html and 'Traité le' in html and 'hx-swap-oob' in html and 'Marquer comme traité' not in html
    assert 'toast' in r['HX-Trigger']


# ---------------------------------------------------------------- données réelles

def test_F67_donnees_reelles_carte_intertitre_effets_et_historique(client, jeu):
    client.force_login(jeu['compte'])
    page = _html(client.get(reverse('site')))
    for attendu in ('Données du site public', 'verrou-effets', 'etat--saisi', 'Suspendue', 'Changements récents', "Voir le journal d", 'grille--principale',
                    'circle-dashed'):
        assert attendu in page, attendu
    assert 'F-60' not in page
    client.post(reverse('donnees-reelles'), {'actif': '1', 'motif': INJECTION}, **HX)
    carte = _html(client.get(reverse('donnees-reelles-etat'), **HX))
    assert 'verrou--ferme' in carte and 'En service' in carte and 'etat--actif' in carte and 'Visibles par tout le monde' in carte
    assert INJECTION not in carte and '&lt;script&gt;' in carte and 'point--vert' in carte


def test_F67_donnees_reelles_modales_conseq_et_alerte_retour(client, jeu):
    client.force_login(jeu['compte'])
    activer = _html(client.get(reverse('donnees-reelles'), **HX))
    assert 'Données d&#x27;exemple' in activer or "Données d'exemple" in activer
    assert 'Activez seulement quand le contenu publié a été relu.' in activer and 'fenamordc.cd' in activer
    client.post(reverse('donnees-reelles'), {'actif': '1'}, **HX)
    retour = _html(client.get(reverse('donnees-reelles'), **HX))
    assert 'alerte--alerte' in retour and 'La vérification des cartes sera suspendue.' in retour
