from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

Usuario = get_user_model()


class RegistroClienteForm(UserCreationForm):
    first_name = forms.CharField(label='Nombres', max_length=150)
    last_name = forms.CharField(label='Apellidos', max_length=150)
    email = forms.EmailField(label='Correo electrónico')
    telefono = forms.CharField(label='Teléfono', max_length=20, required=False)
    dni_ruc = forms.CharField(label='DNI o RUC', max_length=20)

    class Meta:
        model = Usuario
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'telefono',
            'dni_ruc',
            'password1',
            'password2',
        )

    def clean_dni_ruc(self):
        dni = self.cleaned_data['dni_ruc'].strip()
        if Usuario.objects.filter(dni_ruc=dni).exists():
            raise forms.ValidationError('Este DNI/RUC ya está registrado.')
        return dni

    def save(self, commit=True):
        user = super().save(commit=False)
        user.rol = Usuario.ROLE_CLIENTE
        user.email = self.cleaned_data['email']
        user.telefono = self.cleaned_data.get('telefono') or ''
        user.dni_ruc = self.cleaned_data['dni_ruc']
        if commit:
            user.save()
        return user
