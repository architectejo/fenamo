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

    def user_change_password(self, request, id, form_url=''):
        """Mot de passe changé par un super-utilisateur : le titulaire doit le changer à sa prochaine connexion."""
        avant = Compte.objects.filter(pk=id).values_list('password', flat=True).first()
        reponse = super().user_change_password(request, id, form_url)
        if request.method == 'POST' and avant is not None:
            Compte.objects.filter(pk=id).exclude(password=avant).update(doit_changer_mot_de_passe=True)
        return reponse
