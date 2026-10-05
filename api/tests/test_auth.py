"""Inscription, connexion, cookie de refresh et escalade de rôle."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    User,
)


class AuthTests(APITestCase):
    def test_register_user(self):
        url = reverse('register')
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'testpassword123',
            'password2': 'testpassword123',
            'role': 'annotateur'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().username, 'testuser')
        self.assertNotIn('token', response.data)

    def test_login_user(self):
        User.objects.create_user(username='testuser', password='testpassword123', role='annotateur')
        url = reverse('token_obtain_pair')
        data = {
            'username': 'testuser',
            'password': 'testpassword123'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

class RefreshCookieTests(APITestCase):
    """Le refresh token ne circule que dans un cookie HttpOnly."""

    def setUp(self):
        User.objects.create_user(username='testuser', password='testpassword123', role='annotateur')

    def login(self):
        return self.client.post(
            reverse('token_obtain_pair'),
            {'username': 'testuser', 'password': 'testpassword123'},
            format='json',
        )

    def test_login_pose_un_cookie_httponly(self):
        response = self.login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        cookie = response.cookies['refresh_token']
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Strict')
        self.assertEqual(cookie['path'], '/api/token/')

    def test_refresh_avec_cookie_fait_tourner_le_token(self):
        old_token = self.login().cookies['refresh_token'].value
        response = self.client.post(reverse('token_refresh'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        self.assertNotEqual(response.cookies['refresh_token'].value, old_token)

    def test_refresh_sans_cookie_renvoie_401(self):
        response = self.client.post(reverse('token_refresh'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_ancien_refresh_token_est_blackliste(self):
        old_token = self.login().cookies['refresh_token'].value
        self.client.post(reverse('token_refresh'))
        self.client.cookies['refresh_token'] = old_token
        response = self.client.post(reverse('token_refresh'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_revoque_le_refresh_token(self):
        token = self.login().cookies['refresh_token'].value
        response = self.client.post(reverse('token_logout'))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.cookies['refresh_token'].value, '')
        # Même un token copié avant la déconnexion n'est plus utilisable
        self.client.cookies['refresh_token'] = token
        response = self.client.post(reverse('token_refresh'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class RoleEscalationTests(APITestCase):
    """Un utilisateur ne peut jamais s'attribuer un rôle lui-même."""

    def test_inscription_en_admin_ignoree(self):
        self.client.post(reverse('register'), {
            'username': 'pirate', 'email': 'p@example.com',
            'password': 'testpassword123', 'password2': 'testpassword123',
            'role': 'admin',
        }, format='json')
        self.assertEqual(User.objects.get(username='pirate').role, 'annotateur')

    def test_auto_promotion_via_users_me_ignoree(self):
        user = User.objects.create_user(username='u', password='testpassword123', role='annotateur')
        self.client.force_authenticate(user=user)
        response = self.client.patch('/api/users/me/', {'role': 'admin'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.role, 'annotateur')

    def test_auto_promotion_via_users_detail_ignoree(self):
        user = User.objects.create_user(username='u', password='testpassword123', role='annotateur')
        self.client.force_authenticate(user=user)
        self.client.patch(reverse('user-detail', args=[user.id]), {'role': 'admin'}, format='json')
        user.refresh_from_db()
        self.assertEqual(user.role, 'annotateur')
