"""API `/api/v1/` : santé, puis points d'accès du site public sous `site/` (clé du site obligatoire)."""
from django.urls import path, re_path

from api import views, views_site

app_name = 'api'

urlpatterns = [
    path('sante/', views.sante, name='sante'),  # adresse du contrat
    path('', views.sante, name='racine'),  # conservée : sondes de supervision déjà configurées
    path('site/config/', views_site.config, name='site-config'),
    path('site/articles/', views_site.articles, name='site-articles'),
    path('site/articles/<str:slug>/', views_site.article, name='site-article'),
    path('site/galerie/', views_site.galerie, name='site-galerie'),
    path('site/comite/', views_site.comite, name='site-comite'),
    path('site/coordinations/', views_site.coordinations, name='site-coordinations'),
    path('site/statistiques/', views_site.statistiques, name='site-statistiques'),
    path('site/contact/', views_site.contact, name='site-contact'),
    re_path(r'^site/(?P<reste>.*)$', views_site.inconnu, name='site-inconnu'),  # 404 JSON, après la clé
]
