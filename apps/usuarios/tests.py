from django.test import TestCase
from django.contrib.auth import get_user_model

Usuario = get_user_model()

class UsuarioModelTest(TestCase):
    def test_crear_usuario_defecto_cliente(self):
        user = Usuario.objects.create_user(
            username='cliente_test',
            password='testpassword123',
            email='cliente@test.com'
        )
        self.assertEqual(user.rol, Usuario.ROLE_CLIENTE)
        self.assertEqual(user.get_rol_display(), 'Cliente')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_crear_usuario_roles(self):
        vendedor = Usuario.objects.create_user(
            username='vendedor_test',
            password='testpassword123',
            rol=Usuario.ROLE_VENDEDOR
        )
        self.assertEqual(vendedor.rol, Usuario.ROLE_VENDEDOR)
        self.assertEqual(vendedor.get_rol_display(), 'Vendedor')

        tecnico = Usuario.objects.create_user(
            username='tecnico_test',
            password='testpassword123',
            rol=Usuario.ROLE_TECNICO
        )
        self.assertEqual(tecnico.rol, Usuario.ROLE_TECNICO)
        self.assertEqual(tecnico.get_rol_display(), 'Técnico')

        admin = Usuario.objects.create_user(
            username='admin_test',
            password='testpassword123',
            rol=Usuario.ROLE_ADMIN
        )
        self.assertEqual(admin.rol, Usuario.ROLE_ADMIN)
        self.assertEqual(admin.get_rol_display(), 'Administrador')

    def test_crear_superuser(self):
        superuser = Usuario.objects.create_superuser(
            username='super_test',
            password='testpassword123',
            email='super@test.com'
        )
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        # Por defecto los superusuarios se pueden logear como administradores
        self.assertEqual(superuser.rol, Usuario.ROLE_CLIENTE) # rol por defecto es cliente pero is_superuser sobreescribe permisos

class UsuarioLoginRedirectTest(TestCase):
    def setUp(self):
        self.client_user = Usuario.objects.create_user(
            username='cliente_user',
            password='password123',
            rol=Usuario.ROLE_CLIENTE
        )
        self.vendedor_user = Usuario.objects.create_user(
            username='vendedor_user',
            password='password123',
            rol=Usuario.ROLE_VENDEDOR
        )
        self.tecnico_user = Usuario.objects.create_user(
            username='tecnico_user',
            password='password123',
            rol=Usuario.ROLE_TECNICO
        )
        self.admin_user = Usuario.objects.create_user(
            username='admin_user',
            password='password123',
            rol=Usuario.ROLE_ADMIN
        )

    def test_login_redirect_admin(self):
        response = self.client.post('/login/', {
            'username': 'admin_user',
            'password': 'password123'
        })
        self.assertRedirects(response, '/pos/inicio/')

    def test_login_redirect_vendedor(self):
        response = self.client.post('/login/', {
            'username': 'vendedor_user',
            'password': 'password123'
        })
        self.assertRedirects(response, '/pos/inicio/')

    def test_login_redirect_tecnico(self):
        response = self.client.post('/login/', {
            'username': 'tecnico_user',
            'password': 'password123'
        })
        self.assertRedirects(response, '/mantenimiento/')

    def test_login_redirect_cliente(self):
        response = self.client.post('/login/', {
            'username': 'cliente_user',
            'password': 'password123'
        })
        self.assertRedirects(response, '/mi-cuenta/')
