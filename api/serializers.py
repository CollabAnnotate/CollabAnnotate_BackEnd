from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import Project, Dataset, DataItem, Annotation, AnnotationHistory, CommunityAnnotation, ProjectVersion, Notification, ProjectCollaborator, ProjectInvitation
from django.conf import settings
from django.utils import timezone

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'password2', 'first_name', 'last_name', 'role', 'bio']
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

class ProjectSerializer(serializers.ModelSerializer):
    is_published = serializers.BooleanField(read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'created_at', 'created_by',
            'created_by_username', 'status', 'visibility', 'published_at',
            'tags', 'allow_community_annotations', 'is_published'
        ]
        read_only_fields = ['created_by', 'created_at', 'published_at']

    def get_is_published(self, obj):
        return obj.status == 'published'

class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = ['id', 'name', 'description', 'project', 'file', 'uploaded_at']
        read_only_fields = ['uploaded_at']

class DataItemSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    annotations_count = serializers.SerializerMethodField()

    class Meta:
        model = DataItem
        fields = ['id', 'dataset', 'file_path', 'metadata', 'image_url', 'annotations_count', 'image']
        read_only_fields = ['metadata', 'image_url', 'annotations_count']

    def get_image_url(self, obj):
        if obj.image:
            return self.context['request'].build_absolute_uri(obj.image.url)
        return None

    def get_annotations_count(self, obj):
        return obj.annotation_set.count()

class AnnotationSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = Annotation
        fields = [
            'id', 'dataitem', 'label', 'x_min', 'y_min', 'x_max', 'y_max',
            'created_by', 'created_by_username', 'created_at', 'is_validated',
            'validation_status', 'validation_comment'
        ]
        read_only_fields = ['created_by', 'created_at', 'is_validated', 'validation_status']

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
    modified_by_email = serializers.CharField(source='modified_by.email', read_only=True)
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
            'modified_by_email',
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
    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'notification_type', 'content',
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

class ProjectInvitationSerializer(serializers.ModelSerializer):
    invited_by_username = serializers.CharField(source='invited_by.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    expires_in = serializers.SerializerMethodField()

    class Meta:
        model = ProjectInvitation
        fields = ['id', 'project', 'project_name', 'invited_email', 'role', 'invited_by_username',
                 'created_at', 'expires_at', 'status', 'expires_in']
        read_only_fields = ['status', 'token', 'created_at', 'expires_at', 'invited_by']

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