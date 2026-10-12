"""Plan d'URL de l'application web (cahier des charges § 7.3 et annexe B).

Les noms de routes sont conservés : les gabarits, les redirections et `mobapp`
les utilisent. Les adresses sont celles de la cible (racine du domaine).

Les routes qui modifient des données n'acceptent que POST (CSRF) ; la connexion est
exigée partout par LoginRequiredMiddleware.
"""
from django.urls import path

from coptapp.views import *
from coptapp.views.tableau_bord import tableau_bord

urlpatterns = [
    # Tableau de bord
    path('', tableau_bord, name="tableau-bord"),  # § 7.3 : « / » est le tableau de bord

    # Associations membres
    path('associations/', structures_liste, name="str-list"),
    path('associations/mon-association/', session, name="home-session"),
    path('associations/ajouter/', add_structure, name="add-structure"),
    path('associations/<int:id>/', sessionById, name="structure-admin"),
    path('associations/<int:id>/modifier/', edit_structure, name="edit-structure"),
    path('associations/<int:sid>/ville/<int:id>/', ville_attr, name="ville-attr"),
    path('associations/<int:id>/antennes/ajouter/', addAntenne, name="add-antenne"),

    # Coordinations provinciales
    path('provinces/ajouter/', addProvince, name="add-province"),
    path('provinces/<int:id>/', province_view, name="province-view"),
    path('provinces/<int:id>/villes/ajouter/', addVille, name="add-ville"),

    # Villes (niveau hérité, remplacé par l'antenne)
    path('villes/<int:id>/', ville_view, name="ville-view"),
    path('villes/<int:id>/selectionner/', ville_select, name="ville-select"),  # <id> = association

    # Antennes
    path('antennes/<int:id>/', antenneView, name="antenne-view"),
    path('antennes/<int:id>/modifier/', editAntenne, name="edit-antenne"),

    # Membres
    path('membres/', membreListe, name="liste-membre"),
    path('membres/ajouter/', add_membre_from_fenamo, name="add-fenamo-membre"),
    path('membres/ajouter/association/<int:id>/', addMembre, name="add-membre"),
    path('membres/<int:id>/', membre_view, name="membre-view"),
    path('membres/<int:id>/valider/', validate, name="validate"),
    path('membres/<int:id>/supprimer/', demandeSuppression, name="delete-membre"),
    path('membres/<int:idM>/rattachement/association/<int:id>/', structure_attr_membre, name="structure-attribution"),
    path('membres/<int:idM>/rattachement/ville/<int:id>/', ville_attr_membre, name="ville-attribution"),
    path('membres/<int:idM>/rattachement/antenne/<int:id>/', antenne_attr_membre, name="antenne-attribution"),
    path('membres/<int:id>/compte/', viewUser, name="view-user"),
    path('membres/<int:id>/famille/ajouter/', addFamily, name="add-family"),
    path('membres/<int:id>/motos/ajouter/', addMoto, name="add-moto"),

    # Famille
    path('famille/<int:id>/modifier/', editFamily, name="edit-family"),
    path('famille/<int:id>/supprimer/', deleteFamily, name="delete-family"),

    # Engins (motos et tricycles)
    path('motos/<int:id>/', moto_view, name="view-moto"),
    path('motos/<int:id>/modifier/', editMoto, name="edit-moto"),
    path('motos/<int:id>/supprimer/', deleteMoto, name="delete-moto"),
    path('motos/<int:id>/attribuer/', attributMoto, name="moto-attribution"),  # <id> = membre (POST seulement)

    # Compte, recherche, notifications
    path('recherche/', recherche, name="recherche"),
    path('notifications/', notificationsView, name="notifys"),

    # Communiqués
    path('communiques/', listMessage, name="list-message"),
    path('communiques/ajouter/', addCommunique, name="message"),
    path('communiques/<int:id>/', messageView, name="communique"),

    # Contenu du site public
    path('contenu-site/', site, name="site"),
    path('contenu-site/articles/<int:id>/modifier/', article, name="article"),
    path('contenu-site/articles/<int:id>/supprimer/', deleteArticle, name="delete-article"),
    path('contenu-site/messages/', contact, name='contact'),
    path('contenu-site/messages/<int:id>/', contactView, name='contact-view'),
]
