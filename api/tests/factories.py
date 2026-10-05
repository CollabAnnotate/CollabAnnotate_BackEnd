"""Factories factory_boy : fabriquent des objets de test valides en une ligne.

    owner = UserFactory()
    project = ProjectFactory(created_by=owner)
    annotation = AnnotationFactory(dataitem__dataset__project=project)
"""
from datetime import timedelta

import factory
from django.utils import timezone

from api.models import (
    Annotation,
    DataItem,
    Dataset,
    Project,
    ProjectCollaborator,
    ProjectInvitation,
    User,
)

PASSWORD = "Mot-De-Passe-Test-42"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda u: f"{u.username}@example.com")
    role = "annotateur"
    password = factory.django.Password(PASSWORD)


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    name = factory.Sequence(lambda n: f"Projet {n}")
    description = "Projet de test"
    created_by = factory.SubFactory(UserFactory)


class DatasetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Dataset

    name = factory.Sequence(lambda n: f"Dataset {n}")
    type = "image"
    project = factory.SubFactory(ProjectFactory)


class DataItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DataItem

    dataset = factory.SubFactory(DatasetFactory)
    file_path = factory.Sequence(lambda n: f"/images/{n}.jpg")
    metadata = factory.Dict({})


class AnnotationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Annotation

    dataitem = factory.SubFactory(DataItemFactory)
    label = "car"
    x_min, y_min, x_max, y_max = 0.1, 0.1, 0.5, 0.5
    confidence = 1.0
    created_by = factory.SelfAttribute("dataitem.dataset.project.created_by")


class ProjectCollaboratorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjectCollaborator

    project = factory.SubFactory(ProjectFactory)
    user = factory.SubFactory(UserFactory)
    role = "annotator"
    added_by = factory.SelfAttribute("project.created_by")


class ProjectInvitationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjectInvitation

    project = factory.SubFactory(ProjectFactory)
    invited_email = factory.Sequence(lambda n: f"invite{n}@example.com")
    role = "annotator"
    invited_by = factory.SelfAttribute("project.created_by")
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))
    token = factory.Sequence(lambda n: f"token-{n}")
