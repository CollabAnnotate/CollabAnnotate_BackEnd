import os
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.contrib.auth import get_user_model
from ultralytics import YOLO
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Project, Dataset, Annotation
from .serializers import (
    UserSerializer, 
    ProjectSerializer, 
    DatasetSerializer,
    AnnotationSerializer
)

User = get_user_model()

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'role': self.user.role
        }
        return data

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    serializer = UserSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            "status": "error",
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = serializer.save()
        # Générer un token JWT pour l'utilisateur
        refresh = RefreshToken.for_user(user)
        return Response({
            "status": "success",
            "user": UserSerializer(user).data,
            "token": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            "message": "Utilisateur créé avec succès"
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({
            "status": "error",
            "message": str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    
class UserListCreateView(generics.ListCreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]

class ProjectListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return Project.objects.all()
        return Project.objects.filter(created_by=user)

class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return Project.objects.all()
        return Project.objects.filter(created_by=user)

class DatasetListCreateView(generics.ListCreateAPIView):
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Dataset.objects.filter(project__created_by=self.request.user)

class DatasetDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Dataset.objects.filter(project__created_by=self.request.user)

MODEL_PATH = "yolov8n.pt"
model = YOLO(MODEL_PATH)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_and_detect(request):
    try:
        if 'image' not in request.FILES:
            return Response({'error': 'Aucune image envoyée'}, status=400)

        image = request.FILES['image']
        file_path = os.path.join("uploads", image.name)
        path = default_storage.save(file_path, ContentFile(image.read()))
        img_path = default_storage.path(path)

        results = model(img_path)
        detected_objects = []

        for result in results:
            if hasattr(result, 'boxes'):
                for box in result.boxes:
                    detected_objects.append({
                        "x_min": float(box.xyxy[0][0]),
                        "y_min": float(box.xyxy[0][1]),
                        "x_max": float(box.xyxy[0][2]),
                        "y_max": float(box.xyxy[0][3]),
                        "confidence": float(box.conf[0]),
                        "class_id": int(box.cls[0]),
                        "label": model.names[int(box.cls[0])]
                    })

        default_storage.delete(path)
        return Response({"detections": detected_objects}, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_annotations(request):
    try:
        annotations = request.data.get('annotations', [])
        image_id = request.data.get('image_id')
        
        saved_annotations = []
        for ann in annotations:
            serializer = AnnotationSerializer(data={
                'dataitem': ann.get('dataitem_id'),  # Assure-toi que ce champ est fourni
                'image': image_id,
                'label': ann.get('label'),
                'x_min': ann.get('x_min'),
                'y_min': ann.get('y_min'),
                'x_max': ann.get('x_max'),
                'y_max': ann.get('y_max'),
                'confidence': ann.get('confidence')
            }, context={'request': request})
            
            if serializer.is_valid():
                serializer.save()
                saved_annotations.append(serializer.data)
            else:
                return Response(serializer.errors, status=400)

        return Response(saved_annotations, status=201)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_annotations_for_review(request):
    user = request.user
    if user.role not in ['verificateur', 'admin']:
        return Response({"error": "Permission refusée"}, status=403)

    annotations = Annotation.objects.filter(validated=False)
    serializer = AnnotationSerializer(annotations, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_annotation(request, annotation_id):
    user = request.user
    if user.role not in ['verificateur', 'admin']:
        return Response({"error": "Permission refusée"}, status=403)

    try:
        annotation = Annotation.objects.get(id=annotation_id)
        status = request.data.get('status')
        comment = request.data.get('comment', '')

        if status not in ['validé', 'rejeté']:
            return Response({"error": "Statut invalide"}, status=400)

        annotation.validated = True
        annotation.validation_status = status
        annotation.validation_comment = comment
        annotation.validated_by = user
        annotation.save()

        return Response({"message": "Annotation mise à jour avec succès"})
    except Annotation.DoesNotExist:
        return Response({"error": "Annotation non trouvée"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)