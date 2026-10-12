from django.urls import path
from coptapp.views import *


urlpatterns = [
    path('', home, name="home-app"),
    # Structure
    path('add-structure/', add_structure, name="add-structure"),
    path('edit-structure/<int:id>', edit_structure, name="edit-structure"),
    path('ville-attr/<int:id>/<int:sid>', ville_attr, name="ville-attr"),
    path('structure-attribution/<int:id>/<int:idM>', structure_attr_membre, name="structure-attribution"),
    #Session
    path('session', session, name="home-session"),
    path('province-views-datails/<int:id>',province_view,name="province-view"),
    path('add-ville-in-province/<int:id>',addVille,name="add-ville"),
    path('ville-view-details/<int:id>',ville_view,name="ville-view"),
    path('structures-liste/', structures_liste, name="str-list"),
    #Session by ID
    path('my-structure-admin/<int:id>',sessionById,name="structure-admin"),
    #Antenne
    path('add-antenne-in-ville/<int:id>', addAntenne, name="add-antenne"),
    path('edit-antenne/<int:id>', editAntenne, name="edit-antenne"),
    path('antenne-attribution/<int:id>/<int:idM>', antenne_attr_membre, name="antenne-attribution"),
    #Ville
    path('ville-select/<int:id>', ville_select, name="ville-select"),
    path('ville-attribution/<int:id>/<int:idM>/', ville_attr_membre, name="ville-attribution"),
    #Membres
    path('add-membre-from-fenamo/', add_membre_from_fenamo, name="add-fenamo-membre"),
    path('add-membre-in-ville-by-antenne-no-selected/<int:id>', addMembre, name="add-membre"),
    path('view-of-membre-from-city-by-selection/<int:id>', membre_view, name="membre-view"),
    path('add-moto-for-membre-selected/<int:id>', addMoto, name="add-moto"),
    path('delete-moto-for-membre-selected/<int:id>', deleteMoto, name="delete-moto"),
    path('edit-moto-for-membre-selected/<int:id>', editMoto, name="edit-moto"),
    path('sked-to-delete-membre-from-user/<int:id>', demandeSuppression, name="delete-membre"),
    path('view-user-from-membre-by-id/<int:id>', viewUser, name="view-user"),
    path('view-all-notifications-for-user/', notificationsView, name="notifys"),
    path('results-of-seach-on-table/', recherche, name="recherche"),
    path('view-moto-selected-by-meny-to-one/<int:id>', moto_view, name="view-moto"),
    path('add-province-in-app-served-by-admin/', addProvince, name="add-province"),
    path('moto-attribution-for-membre/<int:id>', attributMoto, name="moto-attribution"),
    path('validate-membre-for-any-user/<int:id>', validate, name="validate"),
    path('security-of-user-updated/<int:id>', security, name="security"),
    path('antenne-list-of-membre-by-group-antenne/<int:id>', antenneView, name="antenne-view"),
    path('error-404-generator/', errorPage, name="error"),
    path('add-member-of-family/<int:id>', addFamily, name="add-family"),
    path('edit-family-list/<int:id>', editFamily, name="edit-family"),
    path('delete-family-member/<int:id>', deleteFamily, name="delete-family"),
    path('post-communique-for-user/', addCommunique, name="message"),
    path('list-of-communiques/', listMessage, name="list-message"),
    path('view-of-communique-and-reactions-in-page/<int:id>', messageView, name="communique"),
    path('site-administration/', site, name="site"),
    path('article-edit/<int:id>', article, name="article"),
    path('delete-article/<int:id>', deleteArticle, name="delete-article"),
    path('contact-us-from-site/', contact, name='contact'),
    path('contact-us-from-site-view/<int:id>', contactView, name='contact-view'),
    path('liste-des-membres/', membreListe, name='liste-membre')
]