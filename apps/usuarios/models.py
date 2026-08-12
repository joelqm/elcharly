from django.db import models
from django.contrib.auth.models import AbstractUser

class Usuario(AbstractUser):
    ROLE_ADMIN = 'admin'
    ROLE_VENDEDOR = 'vendedor'
    ROLE_TECNICO = 'tecnico'
    ROLE_CLIENTE = 'cliente'

    ROLES_CHOICES = [
        (ROLE_ADMIN, 'Administrador'),
        (ROLE_VENDEDOR, 'Vendedor'),
        (ROLE_TECNICO, 'Técnico'),
        (ROLE_CLIENTE, 'Cliente'),
    ]

    rol = models.CharField(
        max_length=20,
        choices=ROLES_CHOICES,
        default=ROLE_CLIENTE,
        help_text="Rol del usuario en la plataforma"
    )
    telefono = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono")
    dni_ruc = models.CharField(max_length=20, blank=True, null=True, verbose_name="DNI o RUC")
    sedes = models.ManyToManyField(
        'sistema.Sede',
        blank=True,
        related_name='usuarios',
        verbose_name='Sedes asignadas',
        help_text='Una o ambas sedes (tienda / taller).',
    )
    sede_activa = models.ForeignKey(
        'sistema.Sede',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='usuarios_activos',
        verbose_name='Sede activa',
    )

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return f"{self.username} - {self.get_rol_display()}"

    def save(self, *args, **kwargs):
        if self.rol == self.ROLE_ADMIN:
            self.is_staff = True
        super().save(*args, **kwargs)

    def sedes_permitidas(self):
        if self.is_superuser or self.rol == self.ROLE_ADMIN:
            from apps.sistema.models import Sede
            return Sede.objects.filter(activa=True)
        return self.sedes.filter(activa=True)

