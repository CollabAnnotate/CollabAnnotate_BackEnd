from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    ROLE_CHOICES = [
        ('annotateur', 'Annotateur'),
        ('verificateur', 'Vérificateur'),
        ('admin', 'Administrateur'),
    ]
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default='annotateur')
    bio = models.TextField(blank=True)
    profile_picture = models.ImageField(upload_to='avatars/', null=True, blank=True)
    groups = models.ManyToManyField(Group, related_name="api_user_groups", blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name="api_user_permissions", blank=True)

class Project(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('published', 'Publié'),
        ('archived', 'Archivé'),
    ]
    VISIBILITY_CHOICES = [
        ('private', 'Privé'),
        ('public', 'Public'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='private')
    published_at = models.DateTimeField(null=True, blank=True)
    tags = models.CharField(max_length=500, blank=True)  # Stocké comme une chaîne JSON de tags
    allow_community_annotations = models.BooleanField(default=True)

    def publish(self):
        from django.utils import timezone
        self.status = 'published'
        self.visibility = 'public'
        self.published_at = timezone.now()
        self.save()

    def unpublish(self):
        self.status = 'draft'
        self.visibility = 'private'
        self.published_at = None
        self.save()

class Dataset(models.Model):
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=50)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)

class DataItem(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE)
    file_path = models.CharField(max_length=500, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    image = models.ImageField(upload_to='dataset_images/', null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    created_at = models.DateTimeField(default=timezone.now)

class Label(models.Model):
    dataitem = models.ForeignKey(DataItem, on_delete=models.CASCADE)
    label_type = models.CharField(max_length=50)
    label_data = models.JSONField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

class Annotation(models.Model):
    dataitem = models.ForeignKey(DataItem, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="annotations/", null=True, blank=True)
    label = models.CharField(max_length=100, default="Default Label")
    x_min = models.FloatField(default=0.0)
    y_min = models.FloatField(default=0.0)
    x_max = models.FloatField(default=1.0)
    y_max = models.FloatField(default=1.0)
    confidence = models.FloatField(default=1.0)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_validated = models.BooleanField(default=False)
    validation_status = models.CharField(
        max_length=20, choices=[("validé", "Validé"), ("rejeté", "Rejeté")], null=True, blank=True)
    validation_comment = models.TextField(null=True, blank=True)
    validated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="validated_annotations")
    validated_at = models.DateTimeField(null=True, blank=True)
    last_modified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="last_modified_annotations")
    last_modified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Annotation {self.id} - {self.label}"

    def save(self, *args, **kwargs):
        if not self.pk:  # Si c'est une nouvelle annotation
            super().save(*args, **kwargs)
            # Créer une entrée dans l'historique pour la création
            AnnotationHistory.objects.create(
                annotation=self,
                modified_by=self.created_by,
                modification_type='create'
            )
        else:  # Si c'est une mise à jour
            # Récupérer l'ancienne version
            old_instance = Annotation.objects.get(pk=self.pk)
            super().save(*args, **kwargs)
            # Créer une entrée dans l'historique pour la modification
            if (old_instance.label != self.label or
                old_instance.x_min != self.x_min or
                old_instance.y_min != self.y_min or
                old_instance.x_max != self.x_max or
                old_instance.y_max != self.y_max):
                AnnotationHistory.objects.create(
                    annotation=self,
                    modified_by=self.last_modified_by,
                    modification_type='update',
                    previous_label=old_instance.label,
                    previous_x_min=old_instance.x_min,
                    previous_y_min=old_instance.y_min,
                    previous_x_max=old_instance.x_max,
                    previous_y_max=old_instance.y_max
                )

class AnnotationHistory(models.Model):
    MODIFICATION_TYPES = [
        ('create', 'Création'),
        ('update', 'Modification'),
        ('delete', 'Suppression'),
    ]

    annotation = models.ForeignKey(Annotation, on_delete=models.CASCADE, related_name='history')
    modified_by = models.ForeignKey(User, on_delete=models.CASCADE)
    modified_at = models.DateTimeField(auto_now_add=True)
    modification_type = models.CharField(max_length=20, choices=MODIFICATION_TYPES)

    # Anciennes valeurs
    previous_label = models.CharField(max_length=100, null=True, blank=True)
    previous_x_min = models.FloatField(null=True, blank=True)
    previous_y_min = models.FloatField(null=True, blank=True)
    previous_x_max = models.FloatField(null=True, blank=True)
    previous_y_max = models.FloatField(null=True, blank=True)

    comment = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-modified_at']
        verbose_name_plural = 'Annotation histories'

    def __str__(self):
        return f'Modification de {self.annotation} par {self.modified_by} le {self.modified_at}'

class CommunityAnnotation(models.Model):
    dataitem = models.ForeignKey(DataItem, on_delete=models.CASCADE)
    parent_annotation = models.ForeignKey(
        Annotation, null=True, blank=True, on_delete=models.SET_NULL, related_name='community_responses')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    content = models.TextField()
    coordinates = models.JSONField(null=True, blank=True)  # Pour stocker les coordonnées de l'annotation visuelle
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']

class ProjectVersion(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    changes = models.JSONField()  # Stocke les modifications apportées dans cette version
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('project', 'version_number')
        ordering = ['-version_number']

class Validation(models.Model):
    annotation = models.ForeignKey(Annotation, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=[('validé', 'Validé'), ('rejeté', 'Rejeté')])
    validated_by = models.ForeignKey(User, on_delete=models.CASCADE)
    validated_at = models.DateTimeField(auto_now_add=True)

class Report(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    report_data = models.JSONField()
    generated_by = models.ForeignKey(User, on_delete=models.CASCADE)
    generated_at = models.DateTimeField(auto_now_add=True)

class DetectedObject(models.Model):
    image = models.ImageField(upload_to="detections/")
    label = models.CharField(max_length=100)
    confidence = models.FloatField()
    x_min = models.FloatField()
    y_min = models.FloatField()
    x_max = models.FloatField()
    y_max = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('new_annotation', 'Nouvelle annotation'),
        ('new_response', 'Nouvelle réponse'),
        ('project_published', 'Projet publié'),
        ('annotation_flagged', 'Annotation signalée'),
        ('project_invitation', 'Invitation à un projet'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    content = models.TextField()
    related_project = models.ForeignKey(Project, null=True, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

class ProjectCollaborator(models.Model):
    ROLE_CHOICES = [
        ('viewer', 'Lecteur'),
        ('annotator', 'Annotateur'),
        ('editor', 'Éditeur'),
        ('admin', 'Administrateur'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='collaborators')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_collaborations')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='added_collaborators')
    last_accessed = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('project', 'user')
        ordering = ['added_at']

    def __str__(self):
        return f"{self.user.username} - {self.role} sur {self.project.name}"

class ProjectInvitation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('accepted', 'Acceptée'),
        ('rejected', 'Rejetée'),
        ('expired', 'Expirée'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='invitations')
    invited_email = models.EmailField()
    role = models.CharField(max_length=20, choices=ProjectCollaborator.ROLE_CHOICES)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    token = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invitation pour {self.invited_email} - {self.project.name}"

    def is_expired(self):
        return timezone.now() > self.expires_at

    def accept(self, user):
        if self.status == 'pending' and not self.is_expired():
            ProjectCollaborator.objects.create(
                project=self.project,
                user=user,
                role=self.role,
                added_by=self.invited_by
            )
            self.status = 'accepted'
            self.save()
            return True
        return False
