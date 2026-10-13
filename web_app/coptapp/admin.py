from django.contrib import admin
from coptapp.models import *

# Register your models here.

@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'sigle', 'ordre')
    search_fields = ('nom', 'code', 'sigle')

    def get_readonly_fields(self, request, obj=None):
        # Le code ne change plus dès qu'un engin est numéroté pour la coordination (voir Province.clean).
        return ('code',) if obj is not None and obj.code_fige() else ()


admin.site.register(Ville)


@admin.register(Antenne)
class AntenneAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'coordination', 'type', 'ville_origine')
    list_filter = ('type', 'coordination')
    search_fields = ('nom', 'code')
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