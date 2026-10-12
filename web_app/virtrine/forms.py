from django import forms
from virtrine.models import Article, Config
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Submit

#______Form config

class ConfigForm(forms.ModelForm):

    class Meta:
        model = Config
        fields = '__all__'


    def __init__(self, *args, **kwargs):
        super(ConfigForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        # Ajouter une classe CSS à tous les champs du formulaire
        for field_name, field in self.fields.items():
            self.helper.layout = Layout(Div(field, css_class='col-12 col-sm-6 py-2 wow fadeInRight'))
            field.widget.attrs['class'] = 'form-control'