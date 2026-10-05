from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import (
    User, Project, Dataset, DataItem, Annotation, AnnotationHistory, CommunityAnnotation,
    ProjectCollaborator, Notification, ProjectInvitation,
)
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


class InvitationTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@example.com', password='pw-test-123')
        self.guest = User.objects.create_user(username='guest', email='guest@example.com', password='pw-test-123')
        self.project = Project.objects.create(name='P', description='d', created_by=self.owner)

    def invite(self, email='guest@example.com'):
        return self.client.post(reverse('project-invitation-list'),
                                {'project': self.project.id, 'invited_email': email, 'role': 'annotator'},
                                format='json')

    def test_inviter_un_utilisateur_existant_cree_une_notification(self):
        self.client.force_authenticate(user=self.owner)
        response = self.invite()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = Notification.objects.get(user=self.guest)
        self.assertEqual(notification.notification_type, 'project_invitation')
        self.assertIn('P', notification.content)

    def test_inviter_un_email_inconnu(self):
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.invite('nouveau@example.com').status_code, status.HTTP_201_CREATED)
        self.assertEqual(Notification.objects.count(), 0)

    def test_non_proprietaire_recoit_403_et_non_500(self):
        self.project.status = 'published'
        self.project.save()
        self.client.force_authenticate(user=self.guest)
        self.assertEqual(self.invite('x@example.com').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ProjectInvitation.objects.count(), 0)

    def test_l_invite_accepte_et_devient_collaborateur(self):
        self.client.force_authenticate(user=self.owner)
        invitation_id = self.invite().data['id']
        self.client.force_authenticate(user=self.guest)
        response = self.client.post(reverse('project-invitation-accept', args=[invitation_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(ProjectCollaborator.objects.filter(project=self.project, user=self.guest).exists())


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


class NotificationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u', password='pw-test-123')
        self.other = User.objects.create_user(username='o', password='pw-test-123')
        self.notification = Notification.objects.create(
            user=self.user, notification_type='project_invitation', content='Invité sur P')
        Notification.objects.create(user=self.other, notification_type='new_annotation', content='x')
        self.client.force_authenticate(user=self.user)

    def test_liste_ses_seules_notifications_avec_un_titre(self):
        data = self.client.get(reverse('notification-list')).data
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], 'Invitation à un projet')

    def test_creation_directe_interdite(self):
        response = self.client.post(reverse('notification-list'),
                                    {'notification_type': 'new_annotation', 'content': 'spam'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_marquer_comme_lue(self):
        self.client.post(reverse('notification-mark-as-read', args=[self.notification.id]))
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)


class ProjectResourcesSecurityTests(APITestCase):
    """Images, annotations, historique, équipe et annotations communautaires suivent les droits du projet."""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pw-test-123')
        self.member = User.objects.create_user(username='member', password='pw-test-123')
        self.stranger = User.objects.create_user(username='stranger', password='pw-test-123')
        self.private = Project.objects.create(name='Privé', description='d', created_by=self.owner)
        self.public = Project.objects.create(name='Public', description='d', created_by=self.owner)
        self.public.publish()
        self.private_item = DataItem.objects.create(
            dataset=Dataset.objects.create(name='D', type='image', project=self.private),
            file_path='/a', metadata={})
        self.public_item = DataItem.objects.create(
            dataset=Dataset.objects.create(name='D', type='image', project=self.public),
            file_path='/b', metadata={})
        self.annotation = Annotation.objects.create(
            dataitem=self.private_item, label='car', created_by=self.owner)
        self.membership = ProjectCollaborator.objects.create(
            project=self.private, user=self.member, role='annotator', added_by=self.owner)

    def annotation_payload(self, item):
        return {'dataitem': item.id, 'label': 'x', 'x_min': 0.1, 'y_min': 0.1, 'x_max': 0.2, 'y_max': 0.2}

    # --- (a) historique ---
    def test_historique_d_un_projet_prive_invisible_aux_inconnus(self):
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(reverse('annotation-history-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_historique_sans_email(self):
        self.client.force_authenticate(user=self.owner)
        entry = self.client.get(reverse('annotation-history-list')).data[0]
        self.assertNotIn('modified_by_email', entry)

    # --- (b) équipe ---
    def test_collaborateur_ne_peut_pas_s_auto_promouvoir(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.patch(reverse('project-collaborator-detail', args=[self.membership.id]),
                                     {'role': 'admin'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, 'annotator')

    def test_collaborateur_peut_quitter_le_projet(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.delete(reverse('project-collaborator-detail', args=[self.membership.id]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_proprietaire_change_le_role_d_un_membre(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(reverse('project-collaborator-detail', args=[self.membership.id]),
                                     {'role': 'editor'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filtre_par_projet(self):
        self.client.force_authenticate(user=self.owner)
        url = reverse('project-collaborator-list')
        self.assertEqual(len(self.client.get(url, {'project': self.public.id}).data), 0)
        self.assertEqual(len(self.client.get(url, {'project': self.private.id}).data), 1)

    # --- (d) création dans le projet d'un autre ---
    def test_inconnu_ne_peut_pas_annoter_un_projet_publie(self):
        self.client.force_authenticate(user=self.stranger)
        response = self.client.post(reverse('annotation-list'), self.annotation_payload(self.public_item), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_save_annotations_refuse_un_projet_etranger_en_403(self):
        self.client.force_authenticate(user=self.stranger)
        response = self.client.post(reverse('save_annotations'), {'annotations': [{
            'dataitem_id': self.public_item.id, 'label': 'x',
            'x_min': 0.1, 'y_min': 0.1, 'x_max': 0.2, 'y_max': 0.2, 'confidence': 1}]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_inconnu_ne_peut_pas_ajouter_d_image(self):
        self.client.force_authenticate(user=self.stranger)
        response = self.client.post(reverse('dataitem-list'),
                                    {'dataset': self.public_item.dataset.id, 'file_path': '/x'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_inconnu_ne_peut_pas_supprimer_une_image_publique(self):
        self.client.force_authenticate(user=self.stranger)
        response = self.client.delete(reverse('dataitem-detail', args=[self.public_item.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- (e) les collaborateurs voient et annotent leur projet ---
    def test_annotateur_voit_et_annote_le_projet_prive(self):
        self.client.force_authenticate(user=self.member)
        self.assertEqual(len(self.client.get(reverse('annotation-list')).data), 1)
        response = self.client.post(reverse('annotation-list'), self.annotation_payload(self.private_item), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_annotateur_ne_modifie_pas_l_annotation_d_un_autre(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.patch(reverse('annotation-detail', args=[self.annotation.id]),
                                     {'label': 'pirate'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- historique en double et restauration ---
    def test_une_modification_cree_une_seule_entree_d_historique(self):
        self.client.force_authenticate(user=self.owner)
        self.client.patch(reverse('annotation-detail', args=[self.annotation.id]), {'label': 'bus'}, format='json')
        types = list(AnnotationHistory.objects.filter(annotation=self.annotation)
                     .order_by('modified_at').values_list('modification_type', flat=True))
        self.assertEqual(types, ['create', 'update'])

    def test_restore_sans_modification_renvoie_404(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(reverse('annotation-restore', args=[self.annotation.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_restore_retablit_la_version_precedente(self):
        self.client.force_authenticate(user=self.owner)
        self.client.patch(reverse('annotation-detail', args=[self.annotation.id]), {'label': 'bus'}, format='json')
        self.client.post(reverse('annotation-restore', args=[self.annotation.id]))
        self.annotation.refresh_from_db()
        self.assertEqual(self.annotation.label, 'car')

    # --- (c) annotations communautaires ---
    def test_annotation_communautaire_modifiable_par_son_seul_auteur(self):
        community = CommunityAnnotation.objects.create(
            dataitem=self.public_item, created_by=self.member, content='Il manque un vélo')
        url = reverse('community-annotation-detail', args=[community.id])
        self.client.force_authenticate(user=self.stranger)
        self.assertEqual(self.client.patch(url, {'content': 'spam'}, format='json').status_code,
                         status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_403_FORBIDDEN)
        # Le signalement reste ouvert à tous
        flag_url = reverse('community-annotation-flag', args=[community.id])
        self.assertEqual(self.client.post(flag_url, {'reason': 'hors sujet'}, format='json').status_code,
                         status.HTTP_200_OK)
        # Le propriétaire du projet peut modérer
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)
