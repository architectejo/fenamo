from compte.models import Compte
from django import forms

class AddUserForm(forms.ModelForm):
    class Meta:
        model = Compte
        fields = ['username','email','password']
        labels = {
            'username':"Nom d'utilisateur",
            'email':"E-mail",
            'password':"Mot de passe",
        }

    def __init__(self, *args, **kwargs):
        super(AddUserForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'