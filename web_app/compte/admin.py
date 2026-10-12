from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from compte.models import Compte


@admin.register(Compte)
class CompteAdmin(UserAdmin):
    """Basé sur UserAdmin : le mot de passe est saisi/affiché haché (jamais en clair)."""

    list_display = ('username', 'email', 'membreId', 'is_active', 'is_superuser', 'doit_changer_mot_de_passe')
    list_filter = ('is_active', 'is_superuser', 'doit_changer_mot_de_passe')
    fieldsets = UserAdmin.fieldsets + (
        ('FENAMO-RDC', {'fields': ('membreId', 'doit_changer_mot_de_passe', 'privilege1', 'privilege2',
                                   'privilege3', 'privilege4', 'privilege5', 'privilege', 'editor')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('FENAMO-RDC', {'fields': ('email', 'membreId')}),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            # Compte créé par l'administration : mot de passe saisi par un tiers, à changer à la première connexion.
            obj.doit_changer_mot_de_passe = True
        super().save_model(request, obj, form, change)
