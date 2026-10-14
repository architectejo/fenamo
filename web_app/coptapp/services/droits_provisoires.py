"""RENVOI : les droits sont dans ``compte/services/droits.py`` (rôles et nominations, sous-lot 2e).

Ce module n'existe plus que pour les anciens imports ; il ne contient aucune règle. Les règles hérités (privilege1 à privilege5) sont dans
``compte/services/droits_herites.py``. Importer directement depuis ``compte.services.droits``.
"""
from compte.services.droits import (  # noqa: F401
    antennes_du_perimetre, associations_du_compte, cible_rattachable, droits_membre, engin_pour, engins_visibles,
    est_visiteur, etapes_a_valider, membre_et_droits, membre_pour, membres_du_perimetre, provinces_du_perimetre,
    villes_du_perimetre, voit_tout,
)
