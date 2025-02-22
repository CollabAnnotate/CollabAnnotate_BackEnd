import os
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.contrib.auth import get_user_model
from ultralytics import YOLO
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Project, Dataset, Annotation, AnnotationHistory, CommunityAnnotation, Notification, DataItem
from .serializers import (
    UserSerializer, 
    ProjectSerializer, 
    DatasetSerializer,
    AnnotationSerializer,
    AnnotationHistorySerializer,
    CommunityAnnotationSerializer,
    NotificationSerializer,
    DataItemSerializer
)
from rest_framework import viewsets
from django.db.models import Q
from django.utils import timezone
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

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
    print("Données reçues:", request.data)  # Debug log
    
    # Assurez-vous que le rôle est en minuscules
    if 'role' in request.data and isinstance(request.data['role'], str):
        request.data['role'] = request.data['role'].lower()
    
    serializer = UserSerializer(data=request.data)
    if not serializer.is_valid():
        print("Erreurs de validation:", serializer.errors)  # Debug log
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
        print("Erreur lors de la création:", str(e))  # Debug log
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

class DatasetViewSet(viewsets.ModelViewSet):
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Dataset.objects.filter(
            Q(project__visibility='public') | 
            Q(project__created_by=self.request.user)
        )

    def perform_create(self, serializer):
        serializer.save(project__created_by=self.request.user)

class DataItemViewSet(viewsets.ModelViewSet):
    serializer_class = DataItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return DataItem.objects.filter(
            Q(dataset__project__visibility='public') | 
            Q(dataset__project__created_by=self.request.user)
        )

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
def detect_objects(request):
    try:
        if 'image' not in request.FILES:
            return Response({
                'error': 'Aucune image fournie'
            }, status=status.HTTP_400_BAD_REQUEST)

        image = request.FILES['image']
        
        # Sauvegarder temporairement l'image
        temp_path = default_storage.save('temp_detections/' + image.name, ContentFile(image.read()))
        full_path = default_storage.path(temp_path)

        try:
            # Faire la détection avec YOLO
            results = model(full_path)
            
            # Convertir les résultats en format JSON
            detections = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Convertir les coordonnées en format relatif
                    x1, y1, x2, y2 = box.xyxyn[0].tolist()
                    confidence = float(box.conf[0])
                    class_id = int(box.cls[0])
                    label = result.names[class_id]

                    detections.append({
                        'label': label,
                        'confidence': confidence,
                        'x_min': x1,
                        'y_min': y1,
                        'x_max': x2,
                        'y_max': y2
                    })

            # Nettoyer le fichier temporaire
            default_storage.delete(temp_path)

            return Response({
                'detections': detections
            })

        except Exception as e:
            # Nettoyer en cas d'erreur
            default_storage.delete(temp_path)
            raise e

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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

class AnnotationViewSet(viewsets.ModelViewSet):
    serializer_class = AnnotationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Annotation.objects.filter(
            Q(created_by=self.request.user) | 
            Q(dataitem__dataset__project__created_by=self.request.user)
        )

    def perform_update(self, serializer):
        instance = self.get_object()
        
        # Créer une entrée dans l'historique avant la mise à jour
        AnnotationHistory.objects.create(
            annotation=instance,
            previous_label=instance.label,
            previous_x_min=instance.x_min,
            previous_y_min=instance.y_min,
            previous_x_max=instance.x_max,
            previous_y_max=instance.y_max,
            modified_by=self.request.user,
            modification_type=self.request.data.get('modification_type', 'manual')
        )
        
        # Mettre à jour l'annotation
        serializer.save(
            last_modified_by=self.request.user,
            last_modified_at=timezone.now()
        )

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        annotation = self.get_object()
        history = AnnotationHistory.objects.filter(annotation=annotation)
        serializer = AnnotationHistorySerializer(history, many=True)
        return Response(serializer.data)

class AnnotationHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AnnotationHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AnnotationHistory.objects.filter(
            annotation__created_by=self.request.user
        ).order_by('-modified_at')

class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        user = self.request.user
        return Project.objects.filter(
            Q(created_by=user) | 
            Q(status='published')
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['POST'])
    def add_images(self, request, pk=None):
        project = self.get_object()
        files = request.FILES.getlist('images')
        
        if not files:
            return Response(
                {'error': 'Aucune image fournie'},
                status=status.HTTP_400_BAD_REQUEST
            )

        dataset, created = Dataset.objects.get_or_create(
            project=project,
            defaults={'name': f'Dataset for {project.name}'}
        )
        
        created_items = []
        for file in files:
            data_item = DataItem.objects.create(
                dataset=dataset,
                image=file,
                created_by=request.user
            )
            created_items.append(data_item)
        
        serializer = DataItemSerializer(created_items, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['GET'])
    def get_images(self, request, pk=None):
        project = self.get_object()
        dataset = project.dataset_set.first()
        
        if not dataset:
            return Response([])
            
        data_items = dataset.dataitem_set.all()
        serializer = DataItemSerializer(data_items, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['GET'])
    def get_annotations(self, request, pk=None):
        project = self.get_object()
        annotations = Annotation.objects.filter(dataitem__dataset__project=project)
        serializer = AnnotationSerializer(annotations, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['GET'])
    def stats(self, request, pk=None):
        project = self.get_object()
        dataset = project.dataset_set.first()
        
        stats = {
            'total_images': 0,
            'total_annotations': 0,
            'pending_annotations': 0,
        }
        
        if dataset:
            stats['total_images'] = dataset.dataitem_set.count()
            stats['total_annotations'] = Annotation.objects.filter(
                dataitem__dataset=dataset
            ).count()
            stats['pending_annotations'] = CommunityAnnotation.objects.filter(
                dataitem__dataset=dataset,
                is_flagged=False
            ).count()
        
        return Response(stats)

    @action(detail=True, methods=['POST'])
    def publish(self, request, pk=None):
        project = self.get_object()
        if project.created_by != request.user:
            return Response(
                {'error': 'Non autorisé'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        project.status = 'published'
        project.save()
        return Response({'status': 'published'})

    @action(detail=True, methods=['POST'])
    def unpublish(self, request, pk=None):
        project = self.get_object()
        if project.created_by != request.user:
            return Response(
                {'error': 'Non autorisé'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        project.status = 'draft'
        project.save()
        return Response({'status': 'draft'})

    @action(detail=True, methods=['POST'])
    def detect_objects(self, request, pk=None):
        """
        Détecte les objets dans une image spécifique
        """
        try:
            project = self.get_object()
            image_id = request.data.get('image_id')
            if not image_id:
                return Response({"error": "ID de l'image requis"}, status=400)
                
            data_item = DataItem.objects.get(id=image_id, dataset__project=project)
            image_path = data_item.image.path
            
            # Utiliser YOLO pour détecter les objets
            results = model(image_path)
            detected_objects = []
            
            for result in results:
                if hasattr(result, 'boxes'):
                    for box in result.boxes:
                        detected_objects.append({
                            'label': model.names[int(box.cls[0])],
                            'confidence': float(box.conf[0]),
                            'x_min': float(box.xyxy[0][0]) / data_item.image.width,
                            'y_min': float(box.xyxy[0][1]) / data_item.image.height,
                            'x_max': float(box.xyxy[0][2]) / data_item.image.width,
                            'y_max': float(box.xyxy[0][3]) / data_item.image.height
                        })
            
            return Response(detected_objects)
            
        except DataItem.DoesNotExist:
            return Response({"error": "Image non trouvée"}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

class CommunityAnnotationViewSet(viewsets.ModelViewSet):
    serializer_class = CommunityAnnotationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CommunityAnnotation.objects.filter(
            dataitem__dataset__project__visibility='public'
        )

    def perform_create(self, serializer):
        dataitem = serializer.validated_data['dataitem']
        project = dataitem.dataset.project
        
        if not project.visibility == 'public':
            raise permissions.PermissionDenied(
                "Ce projet n'accepte pas les annotations communautaires"
            )
            
        serializer.save(created_by=self.request.user)
        
        # Créer une notification pour le propriétaire du projet
        Notification.objects.create(
            user=project.created_by,
            notification_type='new_annotation',
            content=f"Nouvelle annotation communautaire sur votre projet {project.name}",
            related_project=project
        )

    @action(detail=True, methods=['post'])
    def flag(self, request, pk=None):
        annotation = self.get_object()
        reason = request.data.get('reason', '')
        
        annotation.is_flagged = True
        annotation.flag_reason = reason
        annotation.save()
        
        # Notifier le propriétaire du projet
        project = annotation.dataitem.dataset.project
        Notification.objects.create(
            user=project.created_by,
            notification_type='annotation_flagged',
            content=f"Une annotation a été signalée dans votre projet {project.name}",
            related_project=project
        )
        
        return Response({"status": "flagged"})

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"status": "marked as read"})

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        Notification.objects.filter(user=request.user).update(is_read=True)
        return Response({"status": "all marked as read"})