from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Project, Dataset, Annotation

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
        fields = ['id', 'dataitem', 'image', 'label', 'x_min', 'y_min', 'x_max', 'y_max', 
                 'confidence', 'created_by', 'created_at', 'validated']
        read_only_fields = ['created_at', 'created_by']

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)