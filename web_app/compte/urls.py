from django.urls import path

from compte import views_journal, views_verrou, views_utilisateurs as vu
from compte.views import add_user, adminer, connexion, deconnexion, securite

urlpatterns = [
    path('connexion/', connexion, name="application"),
    path('deconnexion/', deconnexion, name="deconnexion"),  # POST seulement
    path('membres/<int:id>/creer-compte/', adminer, name="adminer"),  # POST seulement, super-utilisateur
    path('comptes/ajouter/', add_user, name="add-user"),  # super-utilisateur
    path('mon-compte/securite/', securite, name="securite"),
    path('journal/', views_journal.journal, name="journal"),  # F-71, super-utilisateur, lecture seule
    # Verrouillage de l'application (F-07), super-utilisateur seul
    path('application/verrou/', views_verrou.verrou_application, name="verrou-application"),
    path('application/verrou/verrouiller/', views_verrou.verrouiller, name="verrou-verrouiller"),
    path('application/verrou/deverrouiller/', views_verrou.deverrouiller, name="verrou-deverrouiller"),
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
