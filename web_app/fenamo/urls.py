"""Plan d'URL principal (cahier des charges web § 7.3 et annexe B).

L'application est servie à la racine de son domaine.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('gestion-technique/', admin.site.urls),
    path('api/v1/', include('api.urls')),
    path('mob/', include('mobapp.urls')),  # inchangé (§ 2.3)
    path('contenu-site/configuration/', include('virtrine.urls_gestion')),
    path('', include('compte.urls')),
    path('', include('coptapp.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
