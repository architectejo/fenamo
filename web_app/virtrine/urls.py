"""Pages publiques de l'ancien site, retirées de la racine.

Elles ne sont montées que sous `ancien-site/`, le temps que `website/` les
remplace : les gabarits de `mobapp` et du site hérité y font encore référence
(`home`, `news`, `about`...). À supprimer avec ces gabarits.
"""
from django.urls import path

from virtrine.views import about, actualy, article, home, politique, portail

urlpatterns = [
    path('', home, name="home"),
    path('article/<int:id>', article, name="vue-article"),
    path('a-propos-de-nous/', about, name="about"),
    path('activites/', actualy, name="news"),
    path('portail/', portail, name="portail"),
    path('confidentiel/', politique, name="politique"),
]
