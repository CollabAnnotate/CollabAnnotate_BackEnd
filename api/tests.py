from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import User, Project, Dataset, DataItem, Annotation
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