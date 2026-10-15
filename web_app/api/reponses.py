"""Réponses JSON de l'API du site : jamais de cookie, jamais de mise en cache par un intermédiaire sans revalidation."""
from django.http import JsonResponse


def json_ok(donnees, statut=200):
    reponse = JsonResponse(donnees, status=statut, safe=False, json_dumps_params={'ensure_ascii': False})
    reponse.headers['Cache-Control'] = 'no-cache'
    return reponse


def erreur(statut, detail, **entetes):
    reponse = json_ok({'detail': detail}, statut)
    for nom, valeur in entetes.items():
        reponse.headers[nom.replace('_', '-')] = str(valeur)
    return reponse


def champs_invalides(erreurs):
    """400 : ``{"champ": ["message"]}``, affichable à côté des champs par le site."""
    return json_ok({champ: ([m] if isinstance(m, str) else list(m)) for champ, m in erreurs.items()}, 400)


def inactif():
    """403 : les données réelles sont désactivées (le site sert alors son jeu d'exemple)."""
    return json_ok({'statut': 'inactif', 'detail': 'Données réelles désactivées.'}, statut=403)


def introuvable():
    return erreur(404, 'Introuvable.')
