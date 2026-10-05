"""Détection d'objets YOLO (modèle mocké dans conftest.py)."""
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    User,
)


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
