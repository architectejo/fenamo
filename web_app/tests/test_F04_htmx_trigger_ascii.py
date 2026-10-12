"""L'en-tête HX-Trigger reste en ASCII (les en-têtes HTTP ne portent pas l'UTF-8 sûrement) et se relit à l'identique."""
import json

from django.http import HttpResponse

from fenamo.htmx import ajouter_declencheurs, reponse_succes

TEXTE = "L’association membre d’Élodie est enregistrée"


def test_F04_hx_trigger_ascii_et_relisible():
    r = reponse_succes(TEXTE)
    brut = r.headers['HX-Trigger']
    assert brut.isascii() and r'2019' in brut
    assert json.loads(brut)['toast']['message'] == TEXTE


def test_F04_hx_trigger_cumul_de_toasts_en_ascii():
    r = reponse_succes(TEXTE)
    ajouter_declencheurs(r, {'toast': {'message': 'Deuxième ’message’', 'niveau': 'info'}})
    brut = r.headers['HX-Trigger']
    assert brut.isascii()
    assert [t['message'] for t in json.loads(brut)['toast']] == [TEXTE, 'Deuxième ’message’']


def test_F04_hx_trigger_existant_non_ascii_est_repris():
    r = HttpResponse()
    r.headers['HX-Trigger'] = json.dumps({'a': 'x'})
    ajouter_declencheurs(r, {'b': 'é'})
    assert json.loads(r.headers['HX-Trigger']) == {'a': 'x', 'b': 'é'}
