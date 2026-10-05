"""Invitations, notifications et droits sur les ressources d'un projet."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    Annotation,
    AnnotationHistory,
    CommunityAnnotation,
    DataItem,
    Dataset,
    Notification,
    Project,
    ProjectCollaborator,
    ProjectInvitation,
    User,
)


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
