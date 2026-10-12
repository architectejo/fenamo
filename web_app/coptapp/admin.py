from django.contrib import admin
from coptapp.models import *

# Register your models here.

admin.site.register(Province)
admin.site.register(Ville)
admin.site.register(Antenne)
admin.site.register(Communique)
admin.site.register(Reaction)


@admin.register(Membre)
class MembreAdmin(admin.ModelAdmin):
    # Le hachage de Membre.password (mobapp) ne doit jamais s'afficher ni se modifier ici.
    exclude = ('password',)


admin.site.register(Moto)
admin.site.register(Famille)
admin.site.register(Notification)
admin.site.register(AssociationMembre)
#admin.site.register(Error)