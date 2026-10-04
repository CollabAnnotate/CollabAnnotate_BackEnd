from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import User, Project, Dataset, DataItem, Annotation, ProjectCollaborator
from io import BytesIO
from PIL import Image

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


class ProjectPermissionTests(APITestCase):
    """Voir un projet ne donne pas le droit de le modifier."""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pw-test-123')
        self.other = User.objects.create_user(username='other', password='pw-test-123')
        self.published = Project.objects.create(
            name='Publié', description='d', created_by=self.owner, status='published')
        self.private = Project.objects.create(
            name='Privé', description='d', created_by=self.owner)

    def add_collaborator(self, project, user, role):
        ProjectCollaborator.objects.create(project=project, user=user, role=role, added_by=self.owner)

    def url(self, project, action=None):
        if action:
            return reverse(f'project-{action}', args=[project.id])
        return reverse('project-detail', args=[project.id])

    def test_autre_utilisateur_peut_lire_un_projet_publie(self):
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.get(self.url(self.published)).status_code, status.HTTP_200_OK)

    def test_autre_utilisateur_ne_peut_pas_modifier_un_projet_publie(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.patch(self.url(self.published), {'name': 'pirate'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.published.refresh_from_db()
        self.assertEqual(self.published.name, 'Publié')

    def test_autre_utilisateur_ne_peut_pas_supprimer_un_projet_publie(self):
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.delete(self.url(self.published)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Project.objects.filter(id=self.published.id).exists())

    def test_autre_utilisateur_ne_voit_pas_un_projet_prive(self):
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.get(self.url(self.private)).status_code, status.HTTP_404_NOT_FOUND)

    def test_proprietaire_peut_modifier_et_publier(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(self.url(self.private), {'name': 'Renommé'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(self.url(self.private, 'publish'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_collaborateur_editeur_voit_et_modifie_un_projet_prive(self):
        self.add_collaborator(self.private, self.other, 'editor')
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.get(self.url(self.private)).status_code, status.HTTP_200_OK)
        response = self.client.patch(self.url(self.private), {'name': 'Édité'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_collaborateur_editeur_ne_peut_ni_supprimer_ni_publier(self):
        self.add_collaborator(self.private, self.other, 'editor')
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.delete(self.url(self.private)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(self.url(self.private, 'publish')).status_code, status.HTTP_403_FORBIDDEN)

    def test_collaborateur_lecteur_ne_peut_pas_modifier(self):
        self.add_collaborator(self.private, self.other, 'viewer')
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.get(self.url(self.private)).status_code, status.HTTP_200_OK)
        response = self.client.patch(self.url(self.private), {'name': 'x'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_detection_refusee_a_un_non_collaborateur(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.post(self.url(self.published, 'detect-objects'), {'image_id': 1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProjectTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpassword123', role='annotateur')
        self.client.force_authenticate(user=self.user)

    def test_create_project(self):
        url = reverse('project-list')
        data = {
            'name': 'Test Project',
            'description': 'This is a test project',
            'status': 'draft'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(Project.objects.get().name, 'Test Project')

    def test_list_projects(self):
        Project.objects.create(name='Test Project', description='Test Description', created_by=self.user)
        url = reverse('project-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

class YOLOTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpassword123', role='annotateur')
        self.client.force_authenticate(user=self.user)

    def test_upload_and_detect(self):
        url = reverse('detect_objects')
        # Image générée en mémoire : pas de fichier de test à maintenir
        buffer = BytesIO()
        Image.new('RGB', (64, 64), color='white').save(buffer, format='JPEG')
        image = SimpleUploadedFile('test_image.jpg', buffer.getvalue(), content_type='image/jpeg')
        response = self.client.post(url, {'image': image}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('detections', response.data)

class AnnotationTests(APITestCase):
    def setUp(self):
        # Créer un utilisateur pour les tests
        self.user = User.objects.create_user(
            username='testuser',
            password='testpassword123',
            role='annotateur'
        )
        self.client.force_authenticate(user=self.user)

        # Créer un projet pour les tests
        self.project = Project.objects.create(
            name='Test Project',
            description='Test Description',
            created_by=self.user
        )

        # Créer un dataset pour les tests
        self.dataset = Dataset.objects.create(
            name='Test Dataset',
            type='image',
            project=self.project
        )

        # Créer un DataItem pour les tests
        self.dataitem = DataItem.objects.create(
            dataset=self.dataset,  # Utilise le dataset créé
            file_path="/path/to/file",
            metadata={}
        )

    def test_save_annotations(self):
        url = reverse('save_annotations')
        data = {
            "annotations": [
                {
                    "dataitem_id": self.dataitem.id,  # Utilise le DataItem créé
                    "image": 1,
                    "label": "car",
                    "x_min": 0.1,
                    "y_min": 0.2,
                    "x_max": 0.5,
                    "y_max": 0.6,
                    "confidence": 0.9
                }
            ]
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Annotation.objects.count(), 1)
        annotation = Annotation.objects.first()
        self.assertEqual(annotation.label, "car")
        self.assertEqual(annotation.dataitem.id, self.dataitem.id)

    def test_save_annotations_invalid_dataitem(self):
        url = reverse('save_annotations')
        data = {
            "annotations": [
                {
                    "dataitem_id": 999,  # ID qui n'existe pas
                    "image": 1,
                    "label": "car",
                    "x_min": 0.1,
                    "y_min": 0.2,
                    "x_max": 0.5,
                    "y_max": 0.6,
                    "confidence": 0.9
                }
            ]
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Annotation.objects.count(), 0)

class ReviewTests(APITestCase):
    """Écran de révision : liste des annotations à valider et validation."""

    def setUp(self):
        self.annotator = User.objects.create_user(username='annot', password='pw-test-123', role='annotateur')
        self.reviewer = User.objects.create_user(username='verif', password='pw-test-123', role='verificateur')
        project = Project.objects.create(name='P', description='d', created_by=self.annotator)
        dataset = Dataset.objects.create(name='D', type='image', project=project)
        dataitem = DataItem.objects.create(dataset=dataset, file_path='/x', metadata={})
        self.annotation = Annotation.objects.create(
            dataitem=dataitem, label='car', x_min=0.1, y_min=0.1, x_max=0.5, y_max=0.5,
            confidence=0.87, created_by=self.annotator)

    def test_la_route_review_n_est_plus_capturee_par_le_router(self):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.get(reverse('get_annotations_for_review'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['confidence'], 0.87)
        self.assertIn('image_url', response.data[0])

    def test_review_reservee_aux_verificateurs(self):
        self.client.force_authenticate(user=self.annotator)
        response = self.client.get(reverse('get_annotations_for_review'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_validation_enregistre_auteur_et_date(self):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.post(
            reverse('validate_annotation', args=[self.annotation.id]),
            {'status': 'validé', 'comment': 'OK'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.annotation.refresh_from_db()
        self.assertTrue(self.annotation.is_validated)
        self.assertEqual(self.annotation.validation_status, 'validé')
        self.assertEqual(self.annotation.validated_by, self.reviewer)
        self.assertIsNotNone(self.annotation.validated_at)
        # Une fois validée, elle ne figure plus dans la liste à réviser
        self.assertEqual(len(self.client.get(reverse('get_annotations_for_review')).data), 0)

    def test_validation_statut_invalide(self):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.post(
            reverse('validate_annotation', args=[self.annotation.id]), {'status': 'bof'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validation_annotation_inexistante(self):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.post(reverse('validate_annotation', args=[999]), {'status': 'validé'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
