"""Projets : droits, création, statistiques, compteurs et datasets."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    Annotation,
    DataItem,
    Dataset,
    Project,
    ProjectCollaborator,
    User,
)


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


class ProjectStatsTests(APITestCase):
    """Statistiques consommées par les écrans Rapports et Détail du projet."""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pw-test-123')
        self.project = Project.objects.create(name='P', description='d', created_by=self.owner)
        dataset = Dataset.objects.create(name='D', type='image', project=self.project)
        annotated = DataItem.objects.create(dataset=dataset, file_path='/a', metadata={})
        DataItem.objects.create(dataset=dataset, file_path='/b', metadata={})  # image non annotée

        def annotate(label, confidence, validation_status=None):
            Annotation.objects.create(
                dataitem=annotated, label=label, confidence=confidence, created_by=self.owner,
                is_validated=validation_status is not None, validation_status=validation_status)

        annotate('car', 0.9, 'validé')
        annotate('car', 0.7, 'rejeté')
        annotate('person', 0.8)
        self.client.force_authenticate(user=self.owner)

    def test_stats_fournit_les_donnees_des_graphiques(self):
        response = self.client.get(reverse('project-stats', args=[self.project.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        # Compteurs utilisés par ProjectDetail
        self.assertEqual(data['total_images'], 2)
        self.assertEqual(data['total_annotations'], 3)
        self.assertEqual(data['pending_annotations'], 1)
        # Graphiques
        self.assertEqual(data['annotations_by_label'], [
            {'name': 'car', 'value': 2}, {'name': 'person', 'value': 1}])
        self.assertEqual(data['validation_breakdown'], [
            {'name': 'Validées', 'value': 1},
            {'name': 'Rejetées', 'value': 1},
            {'name': 'En attente', 'value': 1}])
        # Indicateurs
        self.assertAlmostEqual(data['quality']['acceptance_rate'], 0.5)
        self.assertAlmostEqual(data['quality']['average_confidence'], 0.8)
        self.assertAlmostEqual(data['quality']['completion_rate'], 0.5)

    def test_stats_projet_vide_sans_division_par_zero(self):
        empty = Project.objects.create(name='Vide', description='d', created_by=self.owner)
        response = self.client.get(reverse('project-stats', args=[empty.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['quality']['acceptance_rate'])
        self.assertIsNone(response.data['quality']['completion_rate'])


class DatasetTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pw-test-123')
        self.other = User.objects.create_user(username='other', password='pw-test-123')
        self.project = Project.objects.create(name='P', description='d', created_by=self.owner)

    def test_creation_dans_son_projet(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(reverse('dataset-list'),
                                    {'name': 'D', 'type': 'image', 'project': self.project.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Dataset.objects.get().project, self.project)

    def test_creation_dans_le_projet_d_un_autre_refusee(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.post(reverse('dataset-list'),
                                    {'name': 'D', 'type': 'image', 'project': self.project.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Dataset.objects.count(), 0)

    def test_creation_dans_un_projet_publie_d_un_autre_refusee(self):
        self.project.status = 'published'
        self.project.save()
        self.client.force_authenticate(user=self.other)
        response = self.client.post(reverse('dataset-list'),
                                    {'name': 'D', 'type': 'image', 'project': self.project.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Dataset.objects.count(), 0)

    def test_modification_par_un_autre_refusee(self):
        self.project.status = 'published'
        self.project.save()
        dataset = Dataset.objects.create(name='D', type='image', project=self.project)
        self.client.force_authenticate(user=self.other)
        response = self.client.patch(reverse('dataset-detail', args=[dataset.id]), {'name': 'x'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProjectListCountersTests(APITestCase):
    """Compteurs affichés par le tableau de bord et la liste des projets."""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pw-test-123')
        self.client.force_authenticate(user=self.owner)
        self.project = Project.objects.create(name='P', description='d', created_by=self.owner)
        dataset = Dataset.objects.create(name='D', type='image', project=self.project)
        item = DataItem.objects.create(dataset=dataset, file_path='/a', metadata={})
        DataItem.objects.create(dataset=dataset, file_path='/b', metadata={})
        Annotation.objects.create(dataitem=item, label='car', created_by=self.owner)
        Annotation.objects.create(dataitem=item, label='car', created_by=self.owner,
                                  is_validated=True, validation_status='validé')

    def test_la_liste_expose_les_compteurs(self):
        project = self.client.get(reverse('project-list')).data[0]
        self.assertEqual(project['total_images'], 2)
        self.assertEqual(project['total_annotations'], 2)
        self.assertEqual(project['pending_annotations'], 1)
        self.assertFalse(project['is_published'])

    def test_creation_renvoie_des_compteurs_a_zero(self):
        response = self.client.post(reverse('project-list'), {'name': 'N', 'description': 'd'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['total_images'], 0)

    def test_creation_publique_publie_le_projet(self):
        response = self.client.post(reverse('project-list'),
                                    {'name': 'N', 'description': 'd', 'visibility': 'public'}, format='json')
        self.assertTrue(response.data['is_published'])
        self.assertEqual(response.data['visibility'], 'public')

    def test_publier_met_a_jour_la_visibilite(self):
        self.client.post(reverse('project-publish', args=[self.project.id]))
        self.project.refresh_from_db()
        self.assertEqual((self.project.status, self.project.visibility), ('published', 'public'))
        self.assertIsNotNone(self.project.published_at)
        self.client.post(reverse('project-unpublish', args=[self.project.id]))
        self.project.refresh_from_db()
        self.assertEqual((self.project.status, self.project.visibility), ('draft', 'private'))
