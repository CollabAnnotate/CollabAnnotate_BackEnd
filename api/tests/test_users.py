"""Back-office des utilisateurs et changement de mot de passe."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    User,
)


class AdminUserTests(APITestCase):
    """Back-office des utilisateurs, réservé au rôle admin."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pw-test-123', role='admin')
        self.annotator = User.objects.create_user(username='annot', password='pw-test-123')
        self.client.force_authenticate(user=self.admin)

    def test_admin_liste_tous_les_utilisateurs(self):
        response = self.client.get(reverse('admin-user-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({u['username'] for u in response.data}, {'admin', 'annot'})

    def test_non_admin_refuse(self):
        self.client.force_authenticate(user=self.annotator)
        self.assertEqual(self.client.get(reverse('admin-user-list')).status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cree_un_utilisateur_avec_mot_de_passe_hache(self):
        response = self.client.post(reverse('admin-user-list'), {
            'username': 'neo', 'email': 'neo@example.com',
            'password': 'Un-Mot-De-Passe-Solide-42', 'role': 'verificateur'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('password', response.data)
        user = User.objects.get(username='neo')
        self.assertEqual(user.role, 'verificateur')
        self.assertTrue(user.check_password('Un-Mot-De-Passe-Solide-42'))

    def test_creation_mot_de_passe_faible_refusee(self):
        response = self.client.post(reverse('admin-user-list'),
                                    {'username': 'neo', 'password': '123', 'role': 'annotateur'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_admin_change_le_role(self):
        response = self.client.patch(reverse('admin-user-detail', args=[self.annotator.id]),
                                     {'role': 'verificateur'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.annotator.refresh_from_db()
        self.assertEqual(self.annotator.role, 'verificateur')

    def test_admin_ne_peut_pas_se_retrograder(self):
        response = self.client.patch(reverse('admin-user-detail', args=[self.admin.id]),
                                     {'role': 'annotateur'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, 'admin')

    def test_admin_ne_peut_pas_se_supprimer(self):
        response = self.client.delete(reverse('admin-user-detail', args=[self.admin.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(User.objects.filter(id=self.admin.id).exists())

    def test_admin_supprime_un_autre_compte(self):
        response = self.client.delete(reverse('admin-user-detail', args=[self.annotator.id]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class PasswordChangeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u', password='Ancien-Mdp-Solide-1')
        self.client.force_authenticate(user=self.user)

    def change(self, current, new):
        return self.client.post('/api/users/me/change-password/',
                                {'current_password': current, 'new_password': new}, format='json')

    def test_mot_de_passe_faible_refuse(self):
        response = self.change('Ancien-Mdp-Solide-1', '123')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Ancien-Mdp-Solide-1'))

    def test_changement_valide(self):
        self.assertEqual(self.change('Ancien-Mdp-Solide-1', 'Nouveau-Mdp-Solide-2').status_code,
                         status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Nouveau-Mdp-Solide-2'))
