from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models
from django.contrib.auth import get_user_model

class User(AbstractUser):
    ROLE_CHOICES = [
        ('annotateur', 'Annotateur'),
        ('verificateur', 'Vérificateur'),
        ('admin', 'Administrateur'),
    ]
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default='annotateur')
    groups = models.ManyToManyField(Group, related_name="api_user_groups", blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name="api_user_permissions", blank=True)

class Project(models.Model):
    STATUS_CHOICES = [
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='en_cours')

class Dataset(models.Model):
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=50)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)

class DataItem(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE)
    file_path = models.CharField(max_length=500)
    metadata = models.JSONField()

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
    validated = models.BooleanField(default=False)
    validation_status = models.CharField(max_length=20, choices=[("validé", "Validé"), ("rejeté", "Rejeté")], null=True, blank=True)
    validation_comment = models.TextField(null=True, blank=True)
    validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="validated_annotations")
    validated_at = models.DateTimeField(null=True, blank=True)

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