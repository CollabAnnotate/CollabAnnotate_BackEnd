"""Vérifie que les factories et fixtures produisent des objets cohérents."""
import pytest

from api.models import AnnotationHistory

from .factories import PASSWORD, AnnotationFactory, ProjectCollaboratorFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_user_factory_hache_le_mot_de_passe():
    user = UserFactory()
    assert user.check_password(PASSWORD)
    assert user.role == "annotateur"


def test_annotation_factory_construit_toute_la_hierarchie():
    annotation = AnnotationFactory()
    project = annotation.dataitem.dataset.project
    assert annotation.created_by == project.created_by
    # Annotation.save() écrit l'entrée d'historique de création
    assert AnnotationHistory.objects.filter(annotation=annotation, modification_type="create").exists()


def test_collaborateur_ajoute_par_le_proprietaire():
    membership = ProjectCollaboratorFactory(role="editor")
    assert membership.added_by == membership.project.created_by


def test_auth_client_est_authentifie(auth_client, user):
    response = auth_client.get("/api/users/me/")
    assert response.status_code == 200
    assert response.data["username"] == user.username
