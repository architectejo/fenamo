"""Pages publiques de l'ancien site, retirées de la racine.

Elles ne sont montées que sous `ancien-site/`, le temps que `website/` les
remplace : les gabarits de `mobapp` et du site hérité y font encore référence
(`home`, `news`, `about`...). À supprimer avec ces gabarits.
"""
from django.contrib.auth.decorators import login_not_required
from django.urls import path

from virtrine.views import about, actualy, article, home, politique, portail

urlpatterns = [
    path('', login_not_required(home), name="home"),
    path('article/<int:id>', login_not_required(article), name="vue-article"),
    path('a-propos-de-nous/', login_not_required(about), name="about"),
    path('activites/', login_not_required(actualy), name="news"),
    path('portail/', login_not_required(portail), name="portail"),
    path('confidentiel/', login_not_required(politique), name="politique"),
]
