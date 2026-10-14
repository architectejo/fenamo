from django.urls import path

from compte import views_utilisateurs as vu
from compte.views import add_user, adminer, connexion, deconnexion, securite

urlpatterns = [
    path('connexion/', connexion, name="application"),
    path('deconnexion/', deconnexion, name="deconnexion"),  # POST seulement
    path('membres/<int:id>/creer-compte/', adminer, name="adminer"),  # POST seulement, super-utilisateur
    path('comptes/ajouter/', add_user, name="add-user"),  # super-utilisateur
    path('mon-compte/securite/', securite, name="securite"),
    # Utilisateurs : nominations, comptes externes, mots de passe temporaires, mandats (F-02, F-03, F-05, F-06)
    path('utilisateurs/', vu.utilisateurs, name="utilisateurs"),
    path('utilisateurs/nommer/', vu.nommer, name="utilisateurs-nommer"),
    path('utilisateurs/membres-nommables/', vu.membres_nommables, name="utilisateurs-membres-nommables"),
    path('utilisateurs/ajouter-externe/', vu.ajouter_externe, name="utilisateurs-externe"),
    path('utilisateurs/<int:id>/reinitialiser/', vu.reinitialiser, name="utilisateurs-reinitialiser"),
    path('utilisateurs/<int:id>/desactiver/', vu.desactiver, name="utilisateurs-desactiver"),
    path('utilisateurs/<int:id>/reactiver/', vu.reactiver, name="utilisateurs-reactiver"),
    path('utilisateurs/<int:id>/role/', vu.changer_role, name="utilisateurs-role"),
    path('utilisateurs/<int:id>/renouveler/', vu.renouveler, name="utilisateurs-renouveler"),
]
