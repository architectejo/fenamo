from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.forms import PasswordChangeForm

from compte.models import Compte


class AddUserForm(forms.ModelForm):
    """Le mot de passe est généré par le service (aucune saisie)."""

    class Meta:
        model = Compte
        fields = ['username', 'email']
        labels = {
            'username': "Nom d'utilisateur",
            'email': "E-mail",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class ChangementMotDePasseForm(PasswordChangeForm):
    """Ancien mot de passe exigé, nouveau mot de passe validé par AUTH_PASSWORD_VALIDATORS."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean_new_password1(self):
        nouveau = self.cleaned_data['new_password1']
        if self.user.check_password(nouveau):
            raise forms.ValidationError(_("Le nouveau mot de passe doit être différent de l'ancien."), code='identique')
        return nouveau
