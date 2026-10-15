"""Modale « Modifier » : valeurs reprises du modèle, renvoyées telles quelles ne changent rien ; modales de suppression avec action et motif."""
import re
from html import unescape

from django.urls import reverse

from coptapp.models import Membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _champs_de_la_modale(html):
    """Valeurs que le navigateur enverrait pour la modale « Modifier » (inputs texte, textarea, selects)."""
    modale = re.search(r'<template id="modale-modifier"[^>]*>(.*?)</template>', html, re.S).group(1)
    donnees = {}
    for balise in re.findall(r'<input name="\w+"[^>]*type="(?:text|tel|email)"[^>]*>', modale):
        nom = re.search(r'name="(\w+)"', balise).group(1)
        valeur = re.search(r'value="([^"]*)"', balise)
        donnees[nom] = unescape(valeur.group(1)) if valeur else ''
    for m in re.finditer(r'<textarea name="(\w+)"[^>]*>(.*?)</textarea>', modale, re.S):
        donnees[m.group(1)] = unescape(m.group(2))
    for m in re.finditer(r'<select name="(\w+)"[^>]*>(.*?)</select>', modale, re.S):
        choisie = re.search(r'<option value="([^"]*)" selected', m.group(2))
        donnees[m.group(1)] = choisie.group(1) if choisie else re.search(r'<option value="([^"]*)"', m.group(2)).group(1)
    return donnees


def test_F21_modifier_sans_changer_conserve_les_valeurs(client, jeu):
    membre = jeu['membre']
    Membre.objects.filter(pk=membre.pk).update(
        nom_epouse='Épouse Fictive', autre_asb='Autre asbl fictive', genre='FEMME', titre='MME', adresse='1 av. Fictive',
        telephone='+243812345678', etat_civil='Marié(e)', qualite='MOTARD', nom_pere='Père Fictif')
    client.force_login(jeu['compte'])
    url = reverse('membre-view', kwargs={'id': membre.id})
    html = client.get(url).content.decode()
    donnees = _champs_de_la_modale(html)
    assert donnees['epouse'] == 'Épouse Fictive' and donnees['autre_asbl'] == 'Autre asbl fictive'
    avant = Membre.objects.get(pk=membre.pk)
    r = client.post(url, {**donnees, 'modifier': '1'})
    assert r.status_code == 200
    apres = Membre.objects.get(pk=membre.pk)
    for champ in ('nom', 'nom_epouse', 'autre_asb', 'genre', 'titre', 'adresse', 'telephone', 'etat_civil', 'qualite', 'nom_pere', 'date_naissance'):
        assert getattr(apres, champ) == getattr(avant, champ), champ


def test_F25_modales_de_suppression_postent_action_et_motif(client, jeu):
    client.force_login(jeu['compte'])
    html = client.get(reverse('membre-view', kwargs={'id': jeu['membre'].id})).content.decode()
    assert 'name="action" value="executer"' in html and 'maxlength="500"' in html and 'data-compteur-motif' in html
    Membre.objects.filter(pk=jeu['membre'].pk).update(etat='supprime', etat_precedent='saisi', motif_suppression='Ancien motif')
    html = client.get(reverse('membre-view', kwargs={'id': jeu['membre'].id})).content.decode()
    assert 'name="action" value="restaurer"' in html
    assert 'Ancien motif' not in html.split('name="action" value="restaurer"')[1].split('</template>')[0]


def test_F28_puces_utilisent_les_codes_et_pluriels_du_service(client, jeu):
    from fenamo.balises import libelle_pluriel_etat
    client.force_login(jeu['compte'])
    html = client.get(reverse('liste-membre')).content.decode()
    assert 'valide-antenne' not in html  # une seule forme de code d'état : snake_case
    for code in ('saisi', 'valide_antenne', 'actif'):
        assert f'value="{code}"' in html and str(libelle_pluriel_etat(code)) in html
