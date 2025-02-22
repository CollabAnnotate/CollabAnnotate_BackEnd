from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import Project, Dataset, DataItem, Annotation, AnnotationHistory, CommunityAnnotation, ProjectVersion, Notification
from django.conf import settings

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    role = serializers.ChoiceField(choices=['annotateur', 'verificateur', 'admin'], default='annotateur')

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'password2', 'role')
        extra_kwargs = {
            'email': {'required': True},
            'username': {'required': True}
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Les mots de passe ne correspondent pas"})
        
        # Validation du mot de passe
        if len(attrs['password']) < 8:
            raise serializers.ValidationError({"password": "Le mot de passe doit contenir au moins 8 caractères"})
        
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data.get('role', 'annotateur')
        )
        return user

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
            'created_by', 'created_by_username', 'created_at', 'validated',
            'validation_status', 'validation_comment'
        ]
        read_only_fields = ['created_by', 'created_at', 'validated', 'validation_status']

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
    class Meta:
        model = AnnotationHistory
        fields = [
            'id', 'annotation', 'previous_label',
            'previous_x_min', 'previous_y_min',
            'previous_x_max', 'previous_y_max',
            'modified_by', 'modified_at',
            'modification_type', 'comment'
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