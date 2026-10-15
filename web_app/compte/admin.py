from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from compte.models import Compte, EtatApplication, JournalAction, Nomination
from compte.services.journal import journaliser


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
        if not change:
            journaliser(request.user, JournalAction.Action.CREATION_COMPTE, obj,
                        apres={'username': obj.username, 'via': 'gestion-technique'})

    def user_change_password(self, request, id, form_url=''):
        """Mot de passe changé par un super-utilisateur : le titulaire doit le changer à sa prochaine connexion."""
        avant = Compte.objects.filter(pk=id).values_list('password', flat=True).first()
        reponse = super().user_change_password(request, id, form_url)
        if request.method == 'POST' and avant is not None:
            if Compte.objects.filter(pk=id).exclude(password=avant).update(doit_changer_mot_de_passe=True):
                journaliser(request.user, JournalAction.Action.CHANGEMENT_MOT_DE_PASSE,
                            Compte.objects.get(pk=id), apres={'changement_impose': True},
                            motif='Mot de passe changé par un super-utilisateur (gestion technique).')
        return reponse


@admin.register(JournalAction)
class JournalActionAdmin(admin.ModelAdmin):
    """Lecture seule : le journal ne se modifie ni ne se supprime."""

    list_display = ('date', 'action', 'auteur', 'role', 'objet_libelle')
    list_filter = ('action',)
    search_fields = ('objet_libelle', 'auteur__username')
    date_hierarchy = 'date'

    def has_view_permission(self, request, obj=None):
        # Le journal contient les actions de tous : seul le super-utilisateur (rôle SU, § 4.1) le consulte.
        return bool(request.user.is_active and request.user.is_superuser)

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Nomination)
class NominationAdmin(admin.ModelAdmin):
    """Nominations : consultation réservée au super-utilisateur, en LECTURE SEULE (les écritures passent par compte.services.nominations)."""

    list_display = ('compte', 'role', 'coordination', 'antenne', 'association', 'debut', 'fin', 'active')
    list_filter = ('role', 'active')
    search_fields = ('compte__username',)

    def _su(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_module_permission(self, request):
        return self._su(request)

    def has_view_permission(self, request, obj=None):
        return self._su(request)

    # Lecture seule : créer, modifier ou terminer une nomination passe par les services (journal, groupes miroirs, contrôles).
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # une nomination terminée se conserve ; elle ne s'efface pas


@admin.register(EtatApplication)
class EtatApplicationAdmin(admin.ModelAdmin):
    """Lecture seule, super-utilisateur : le verrou se pose et se lève par l'écran dédié ou la commande d'urgence (journalisés), jamais ici."""

    list_display = ('verrouillee', 'depuis', 'par')

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
