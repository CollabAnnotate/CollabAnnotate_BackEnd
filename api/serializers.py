from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .models import (
    Annotation,
    AnnotationHistory,
    CommunityAnnotation,
    DataItem,
    Dataset,
    Notification,
    Project,
    ProjectCollaborator,
    ProjectInvitation,
    ProjectVersion,
)
from .permissions import ANNOTATOR_ROLES, EDITOR_ROLES, has_project_role

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'password2', 'first_name', 'last_name', 'role', 'bio',
                  'profile_picture']
        # Le rôle donne des droits (validation, accès admin) : jamais modifiable par
        # l'utilisateur lui-même. Il s'attribue via l'interface /admin/ de Django.
        read_only_fields = ['id', 'role']
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False},
            'bio': {'required': False},
        }

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('password2'):
            raise serializers.ValidationError({"password": "Les mots de passe ne correspondent pas"})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        if 'password' in validated_data:
            password = validated_data.pop('password')
            validated_data.pop('password2', None)
            instance.set_password(password)
        return super().update(instance, validated_data)

class AdminUserSerializer(serializers.ModelSerializer):
    """Back-office des administrateurs : contrairement à UserSerializer, le rôle est modifiable."""
    password = serializers.CharField(write_only=True, required=False, validators=[validate_password])

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role',
                  'is_active', 'password', 'date_joined', 'last_login']
        read_only_fields = ['id', 'date_joined', 'last_login']

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'Obligatoire à la création.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)

class ProjectSerializer(serializers.ModelSerializer):
    is_published = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    # Compteurs annotés par ProjectViewSet.get_queryset ; 0 sur un projet tout juste créé
    total_images = serializers.SerializerMethodField()
    total_annotations = serializers.SerializerMethodField()
    pending_annotations = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'created_at', 'created_by',
            'created_by_username', 'status', 'visibility', 'published_at',
            'tags', 'allow_community_annotations', 'is_published',
            'total_images', 'total_annotations', 'pending_annotations'
        ]
        # Statut et visibilité changent via les actions publish/unpublish
        read_only_fields = ['created_by', 'created_at', 'published_at', 'status', 'visibility']

    def get_is_published(self, obj):
        return obj.status == 'published'

    def get_total_images(self, obj):
        return getattr(obj, 'total_images', 0)

    def get_total_annotations(self, obj):
        return getattr(obj, 'total_annotations', 0)

    def get_pending_annotations(self, obj):
        return getattr(obj, 'pending_annotations', 0)

class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = ['id', 'name', 'type', 'project']

    def validate_project(self, project):
        """On ne crée ou déplace un dataset que dans un projet dont on est éditeur."""
        user = self.context['request'].user
        if not has_project_role(user, project, EDITOR_ROLES):
            raise PermissionDenied("Vous n'avez pas les droits nécessaires sur ce projet.")
        return project

class DataItemSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    annotations_count = serializers.SerializerMethodField()

    class Meta:
        model = DataItem
        fields = ['id', 'dataset', 'file_path', 'metadata', 'image_url', 'annotations_count', 'image']
        read_only_fields = ['metadata', 'image_url', 'annotations_count']

    def validate_dataset(self, dataset):
        """On n'ajoute d'images que dans un projet dont on est éditeur."""
        if not has_project_role(self.context['request'].user, dataset.project, EDITOR_ROLES):
            raise PermissionDenied("Vous n'avez pas les droits nécessaires sur ce projet.")
        return dataset

    def get_image_url(self, obj):
        if obj.image:
            return self.context['request'].build_absolute_uri(obj.image.url)
        return None

    def get_annotations_count(self, obj):
        return obj.annotation_set.count()

class AnnotationSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Annotation
        fields = [
            'id', 'dataitem', 'image_url', 'label', 'x_min', 'y_min', 'x_max', 'y_max',
            'confidence', 'created_by', 'created_by_username', 'created_at', 'is_validated',
            'validation_status', 'validation_comment', 'validated_by', 'validated_at'
        ]
        read_only_fields = [
            'created_by', 'created_at', 'is_validated', 'validation_status',
            'validation_comment', 'validated_by', 'validated_at'
        ]

    def validate_dataitem(self, dataitem):
        """On n'annote que les images d'un projet où l'on est au moins annotateur."""
        if not has_project_role(self.context['request'].user, dataitem.dataset.project, ANNOTATOR_ROLES):
            raise PermissionDenied("Vous n'êtes pas annotateur de ce projet.")
        return dataitem

    def get_image_url(self, obj):
        """URL absolue de l'image annotée (portée par le DataItem)."""
        image = obj.dataitem.image
        if not image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(image.url) if request else image.url

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Sauvegarder qui a fait la modification
        request = self.context.get('request')
        if request and request.user:
            validated_data['last_modified_by'] = request.user

        return super().update(instance, validated_data)

    def validate(self, data):
        # Valider que les coordonnées sont dans les bonnes plages
        if 'x_min' in data and 'x_max' in data:
            if data['x_min'] >= data['x_max']:
                raise serializers.ValidationError("x_min doit être inférieur à x_max")
            if data['x_min'] < 0 or data['x_max'] > 1:
                raise serializers.ValidationError("Les coordonnées x doivent être entre 0 et 1")

        if 'y_min' in data and 'y_max' in data:
            if data['y_min'] >= data['y_max']:
                raise serializers.ValidationError("y_min doit être inférieur à y_max")
            if data['y_min'] < 0 or data['y_max'] > 1:
                raise serializers.ValidationError("Les coordonnées y doivent être entre 0 et 1")

        return data

class AnnotationHistorySerializer(serializers.ModelSerializer):
    modified_by_username = serializers.CharField(source='modified_by.username', read_only=True)
    modified_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = AnnotationHistory
        fields = [
            'id',
            'annotation',
            'previous_label',
            'previous_x_min',
            'previous_y_min',
            'previous_x_max',
            'previous_y_max',
            'modified_by',
            'modified_by_username',
            'modified_at',
            'modification_type'
        ]
        read_only_fields = ['modified_at', 'modified_by']

class CommunityAnnotationSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = CommunityAnnotation
        fields = [
            'id', 'dataitem', 'parent_annotation', 'created_by',
            'created_by_username', 'created_at', 'content', 'coordinates',
            'is_flagged', 'flag_reason'
        ]
        read_only_fields = ['created_by', 'created_at', 'is_flagged', 'flag_reason']

class ProjectVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectVersion
        fields = [
            'id', 'project', 'version_number', 'created_at',
            'changes', 'created_by'
        ]
        read_only_fields = ['created_by', 'created_at', 'version_number']

class NotificationSerializer(serializers.ModelSerializer):
    # Libellé lisible du type, ex. « Invitation à un projet »
    title = serializers.CharField(source='get_notification_type_display', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'notification_type', 'title', 'content',
            'related_project', 'created_at', 'is_read'
        ]
        read_only_fields = ['user', 'created_at']

class ProjectCollaboratorSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = ProjectCollaborator
        fields = ['id', 'user', 'user_id', 'project', 'project_name', 'role', 'added_at', 'last_accessed']
        read_only_fields = ['added_at', 'last_accessed']

    def validate(self, attrs):
        # Projet et utilisateur sont fixés à la création : seul le rôle évolue ensuite
        if self.instance is not None:
            attrs.pop('project', None)
            attrs.pop('user_id', None)
        return attrs

class ProjectInvitationSerializer(serializers.ModelSerializer):
    invited_by_username = serializers.CharField(source='invited_by.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    expires_in = serializers.SerializerMethodField()

    class Meta:
        model = ProjectInvitation
        fields = ['id', 'project', 'project_name', 'invited_email', 'role', 'invited_by_username',
                 'created_at', 'expires_at', 'status', 'expires_in']
        read_only_fields = ['status', 'token', 'created_at', 'expires_at', 'invited_by']

    def validate_project(self, project):
        # Vérifié avant validate() : un non-gestionnaire ne doit rien apprendre de l'équipe
        if not has_project_role(self.context['request'].user, project, ('admin',)):
            raise PermissionDenied("Vous n'avez pas la permission d'inviter des collaborateurs sur ce projet")
        return project

    def validate(self, data):
        # Vérifier si l'email existe déjà comme collaborateur du projet
        project = data.get('project')
        invited_email = data.get('invited_email')

        if ProjectCollaborator.objects.filter(
            project=project,
            user__email=invited_email
        ).exists():
            raise serializers.ValidationError(
                "Cet utilisateur est déjà collaborateur du projet"
            )

        # Vérifier si une invitation en attente existe déjà
        if ProjectInvitation.objects.filter(
            project=project,
            invited_email=invited_email,
            status='pending'
        ).exists():
            raise serializers.ValidationError(
                "Une invitation est déjà en attente pour cet email"
            )

        return data

    def get_expires_in(self, obj):
        if obj.expires_at and obj.status == 'pending':
            now = timezone.now()
            if now < obj.expires_at:
                time_left = obj.expires_at - now
                return int(time_left.total_seconds())
        return 0
