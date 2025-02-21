from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Project, Dataset, Annotation, AnnotationHistory

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=True)
    role = serializers.ChoiceField(choices=['annotateur', 'verificateur', 'admin'], default='annotateur')

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'role')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        role = validated_data.pop('role', 'annotateur')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        user.role = role
        user.save()
        return user

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'created_by', 'status']
        read_only_fields = ['created_by']  # created_by ne peut pas être modifié manuellement

    def create(self, validated_data):
        # Assigner l'utilisateur actuel à created_by
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)

class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = ['id', 'name', 'description', 'project', 'file', 'uploaded_at']
        read_only_fields = ['uploaded_at']


class AnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Annotation
        fields = [
            'id', 'dataitem', 'image', 'label',
            'x_min', 'y_min', 'x_max', 'y_max',
            'confidence', 'created_by', 'created_at',
            'last_modified_at', 'last_modified_by',
            'is_ai_generated', 'validated', 'validation_status',
            'validation_comment', 'validated_by', 'validated_at'
        ]
        read_only_fields = ['created_at', 'created_by', 'last_modified_at']

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