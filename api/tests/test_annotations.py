"""Annotations : sauvegarde en lot et écran de révision."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    Annotation,
    DataItem,
    Dataset,
    Project,
    User,
)


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
