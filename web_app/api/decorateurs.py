"""Décorateur des points d'accès ``/api/v1/site/`` : clé du site, limite de débit, méthodes.

Ordre des contrôles (le verrou F-07 passe avant, dans le middleware) : clé (401) -> limite de débit (429) -> méthode (405).
Aucune session ni cookie : la réponse est débarrassée de tout cookie, et la vue est exemptée de la connexion et du CSRF
(l'authentification est la clé, pas un cookie)."""
import functools
import logging

from django.contrib.auth.decorators import login_not_required
from django.views.decorators.csrf import csrf_exempt

from api import reponses
from api.services import cles, limites

logger = logging.getLogger('api.cles')
ENTETE_CLE = 'X-Site-Key'


def cle_site_requise(methodes=('GET',)):
    """`methodes=None` : toutes les méthodes sont transmises à la vue (route inconnue)."""
    def decorateur(vue):
        @functools.wraps(vue)
        def enveloppe(request, *args, **kwargs):
            cle = request.headers.get(ENTETE_CLE, '')
            identite = cles.verifier(cle)
            if identite is None:
                # Jamais la clé elle-même dans le journal : seulement le préfixe s'il a le bon format.
                logger.warning("Clé du site refusée : adresse %s, %s %s, préfixe %s.", request.META.get('REMOTE_ADDR', '?'),
                               request.method, request.path, cles.extraire_prefixe(cle) or ('absent' if not cle else 'invalide'))
                reponse = reponses.erreur(401, 'Clé du site absente ou invalide.')
            else:
                nature, objet = identite
                attente = limites.controler(objet.prefixe if objet else 'dev', request.method)
                if attente is not None:
                    reponse = reponses.erreur(429, 'Trop de requêtes.', Retry_After=attente)
                elif methodes is not None and request.method not in methodes:
                    reponse = reponses.erreur(405, 'Méthode non permise.', Allow=', '.join(methodes))
                else:
                    reponse = vue(request, *args, **kwargs)
            reponse.cookies.clear()
            reponse.headers['Cache-Control'] = 'no-cache'
            return reponse
        return login_not_required(csrf_exempt(enveloppe))
    return decorateur
