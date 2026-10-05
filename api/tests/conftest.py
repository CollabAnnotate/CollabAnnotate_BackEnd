"""Fixtures partagées par tous les tests (injectées par pytest d'après leur nom)."""
from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIClient

from .factories import ProjectFactory, UserFactory


@pytest.fixture(autouse=True)
def media_root_temporaire(settings, tmp_path):
    """Les fichiers envoyés pendant les tests ne polluent pas le vrai dossier media/."""
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(autouse=True)
def yolo_mock(monkeypatch):
    """Remplace le modèle YOLO : pas de torch ni de poids à charger, tests rapides et déterministes.

    Par défaut le modèle ne détecte rien ; un test peut fixer `yolo_mock.return_value`
    pour simuler des détections.
    """
    model = MagicMock(name="yolo_model")
    model.return_value = []
    model.names = {0: "person", 2: "car"}
    monkeypatch.setattr("api.views.get_model", lambda: model)
    return model


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def auth_client(api_client, user):
    """Client authentifié en tant que `user`."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def project(user):
    """Projet privé appartenant à `user`."""
    return ProjectFactory(created_by=user)
