import os
from functools import lru_cache
from rest_framework import generics, permissions, status, viewsets, serializers
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from rest_framework_simplejwt.tokens import RefreshToken
from .permissions import ProjectPermission
from .models import Project, Dataset, Annotation, AnnotationHistory, CommunityAnnotation, Notification, DataItem, ProjectCollaborator, ProjectInvitation
from .serializers import (
    UserSerializer, 
    ProjectSerializer, 
    DatasetSerializer,
    AnnotationSerializer,
    AnnotationHistorySerializer,
    CommunityAnnotationSerializer,
    NotificationSerializer,
    DataItemSerializer,
    ProjectCollaboratorSerializer,
    ProjectInvitationSerializer
)
from rest_framework import viewsets
from django.db.models import Q
from django.utils import timezone
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.exceptions import PermissionDenied
from django.db import models

User = get_user_model()

def set_refresh_cookie(response, refresh_token):
    """Place le refresh token dans un cookie HttpOnly (voir JWT_REFRESH_COOKIE)."""
    response.set_cookie(value=refresh_token, **settings.JWT_REFRESH_COOKIE)


def delete_refresh_cookie(response):
    cookie = settings.JWT_REFRESH_COOKIE
    response.delete_cookie(cookie['key'], path=cookie['path'], samesite=cookie['samesite'])


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # Le parent fournit déjà 'access' et 'refresh'
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'role': self.user.role
        }
        return data

class MyTokenObtainPairView(TokenObtainPairView):
    """Connexion : l'access token est renvoyé en JSON, le refresh token en cookie HttpOnly."""
    serializer_class = MyTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        set_refresh_cookie(response, response.data.pop('refresh'))
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """Refresh : lit le refresh token dans le cookie et le fait tourner (rotation + blacklist)."""

    def post(self, request, *args, **kwargs):
        refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE['key'])
        if not refresh:
            raise InvalidToken('Aucun refresh token')

        serializer = self.get_serializer(data={'refresh': refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0]) from e

        data = dict(serializer.validated_data)
        new_refresh = data.pop('refresh', None)
        response = Response(data, status=status.HTTP_200_OK)
        if new_refresh:
            set_refresh_cookie(response, new_refresh)
        return response


class LogoutView(APIView):
    """Déconnexion : blackliste le refresh token du cookie puis supprime le cookie."""
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE['key'])
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass  # déjà expiré ou blacklisté : rien à révoquer
        response = Response(status=status.HTTP_204_NO_CONTENT)
        delete_refresh_cookie(response)
        return response


@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    try:
        # Le rôle envoyé est ignoré (read_only) : tout nouvel inscrit est annotateur
        serializer = UserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = serializer.save()

        # Pas de tokens ici : l'utilisateur se connecte ensuite via token/
        return Response({
            "status": "success",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role
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

class DatasetViewSet(viewsets.ModelViewSet):
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Dataset.objects.all()

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
    queryset = DataItem.objects.all()

    def get_queryset(self):
        return DataItem.objects.filter(
            Q(dataset__project__visibility='public') | 
            Q(dataset__project__created_by=self.request.user)
        )

MODEL_PATH = "yolov8n.pt"

@lru_cache(maxsize=1)
def get_model():
    """Charge le modèle YOLO au premier appel seulement (torch est lourd en mémoire)."""
    from ultralytics import YOLO
    return YOLO(MODEL_PATH)

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

        model = get_model()
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
            results = get_model()(full_path)
            
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

    annotations = Annotation.objects.filter(is_validated=False)
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

        annotation.is_validated = True
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
    queryset = Annotation.objects.all()

    def get_queryset(self):
        dataitem_id = self.request.query_params.get('dataitem', None)
        queryset = Annotation.objects.filter(
            Q(created_by=self.request.user) | 
            Q(dataitem__dataset__project__created_by=self.request.user)
        )
        
        if dataitem_id:
            queryset = queryset.filter(dataitem_id=dataitem_id)
            
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

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
        return serializer.save(
            last_modified_by=self.request.user,
            last_modified_at=timezone.now()
        )

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        annotation = self.get_object()
        history = AnnotationHistory.objects.filter(annotation=annotation)
        serializer = AnnotationHistorySerializer(history, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        annotation = self.get_object()
        history = AnnotationHistory.objects.filter(annotation=annotation).latest('modified_at')
        
        annotation.label = history.previous_label
        annotation.x_min = history.previous_x_min
        annotation.y_min = history.previous_y_min
        annotation.x_max = history.previous_x_max
        annotation.y_max = history.previous_y_max
        annotation.save()
        
        return Response({"message": "Annotation restaurée avec succès"})

class AnnotationHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AnnotationHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = AnnotationHistory.objects.all()

    def get_queryset(self):
        annotation_id = self.request.query_params.get('annotation', None)
        queryset = super().get_queryset()
        
        if annotation_id:
            queryset = queryset.filter(annotation_id=annotation_id)
            
        return queryset.order_by('-modified_at')

class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    # Être visible ne suffit pas pour modifier : voir api/permissions.py
    permission_classes = [permissions.IsAuthenticated, ProjectPermission]
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    queryset = Project.objects.all()

    def get_queryset(self):
        """Projets visibles : les siens, ceux où l'on collabore, et les projets publiés."""
        user = self.request.user
        return Project.objects.filter(
            Q(created_by=user) |
            Q(collaborators__user=user) |
            Q(status='published')
        ).distinct()

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
        datasets = Dataset.objects.filter(project=project)
        dataitems = DataItem.objects.filter(dataset__in=datasets)
        annotations = Annotation.objects.filter(dataitem__in=dataitems)
        collaborators = ProjectCollaborator.objects.filter(project=project)

        stats = {
            'total_images': dataitems.count(),
            'total_annotations': annotations.count(),
            'pending_annotations': annotations.filter(is_validated=False).count(),
            'total_collaborators': collaborators.count() + 1,  # +1 pour inclure le créateur
            'validated_annotations': annotations.filter(is_validated=True).count(),
            'rejected_annotations': annotations.filter(validation_status='rejeté').count(),
        }

        return Response(stats)

    @action(detail=True, methods=['POST'])
    def publish(self, request, pk=None):
        # Réservé au propriétaire : contrôlé par ProjectPermission dans get_object()
        project = self.get_object()
        project.status = 'published'
        project.save()
        return Response({'status': 'published'})

    @action(detail=True, methods=['POST'])
    def unpublish(self, request, pk=None):
        project = self.get_object()
        project.status = 'draft'
        project.save()
        return Response({'status': 'draft'})

    @action(detail=True, methods=['POST'])
    def detect_objects(self, request, pk=None):
        """
        Détecte les objets dans une image spécifique
        """
        # Hors du try : un refus de permission doit donner 403, pas 500
        project = self.get_object()
        try:
            image_id = request.data.get('image_id')
            if not image_id:
                return Response({"error": "ID de l'image requis"}, status=400)
                
            data_item = DataItem.objects.get(id=image_id, dataset__project=project)
            image_path = data_item.image.path
            
            # Utiliser YOLO pour détecter les objets
            model = get_model()
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
    queryset = CommunityAnnotation.objects.all()

    def get_queryset(self):
        return CommunityAnnotation.objects.filter(
            dataitem__dataset__project__visibility='public'
        )

    def perform_create(self, serializer):
        dataitem = serializer.validated_data['dataitem']
        project = dataitem.dataset.project
        
        if not project.visibility == 'public':
            raise PermissionDenied(
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

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Notification.objects.all()

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

class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    queryset = User.objects.all()
    
    def get_queryset(self):
        return get_user_model().objects.filter(id=self.request.user.id)
    
    @action(detail=False, methods=['get', 'patch'])
    def me(self, request):
        if request.method == 'GET':
            serializer = self.get_serializer(request.user)
            return Response(serializer.data)
        elif request.method == 'PATCH':
            serializer = self.get_serializer(request.user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], url_path='me/change-password')
    def change_password(self, request):
        user = request.user
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        
        if not current_password or not new_password:
            return Response(
                {'error': 'Les deux mots de passe sont requis'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not user.check_password(current_password):
            return Response(
                {'error': 'Mot de passe actuel incorrect'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.password = make_password(new_password)
        user.save()
        return Response({'message': 'Mot de passe modifié avec succès'})

class ProjectCollaboratorViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectCollaboratorSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ProjectCollaborator.objects.filter(
            models.Q(project__created_by=self.request.user) |
            models.Q(user=self.request.user)
        )

    def perform_create(self, serializer):
        project = serializer.validated_data['project']
        if project.created_by != self.request.user:
            raise PermissionDenied("Seul le créateur du projet peut ajouter des collaborateurs")
        serializer.save(added_by=self.request.user)

    @action(detail=False, methods=['get'])
    def my_collaborations(self, request):
        collaborations = ProjectCollaborator.objects.filter(user=request.user)
        serializer = self.get_serializer(collaborations, many=True)
        return Response(serializer.data)

class ProjectInvitationViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectInvitationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return ProjectInvitation.objects.filter(
            models.Q(project__created_by=self.request.user) |
            models.Q(invited_email=self.request.user.email)
        )

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            project = serializer.validated_data['project']
            invited_email = serializer.validated_data['invited_email']
            
            # Vérifier si l'utilisateur est le créateur du projet ou un admin
            is_creator = project.created_by == request.user
            is_admin = ProjectCollaborator.objects.filter(
                project=project,
                user=request.user,
                role='admin'
            ).exists()
            
            if not (is_creator or is_admin):
                raise PermissionDenied("Vous n'avez pas la permission d'inviter des collaborateurs sur ce projet")
            
            # Générer un token unique
            import secrets
            token = secrets.token_urlsafe(32)
            
            # Définir une date d'expiration (7 jours)
            from django.utils import timezone
            import datetime
            expires_at = timezone.now() + datetime.timedelta(days=7)
            
            invitation = serializer.save(
                invited_by=request.user,
                token=token,
                expires_at=expires_at,
                status='pending'
            )
            
            # Créer une notification pour l'utilisateur invité s'il existe
            User = get_user_model()
            try:
                invited_user = User.objects.get(email=invitation.invited_email)
                Notification.objects.create(
                    user=invited_user,
                    type='project_invitation',
                    message=f"Vous avez été invité à collaborer sur le projet {project.name}",
                    related_project=project
                )
            except User.DoesNotExist:
                pass
                
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except serializers.ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        invitation = self.get_object()
        
        if invitation.invited_email != request.user.email:
            raise PermissionDenied("Cette invitation ne vous est pas destinée")
        
        if invitation.status != 'pending':
            raise serializers.ValidationError("Cette invitation n'est plus valide")
            
        if invitation.is_expired():
            raise serializers.ValidationError("Cette invitation a expiré")
            
        try:
            invitation.accept(request.user)
            return Response({"message": "Invitation acceptée avec succès"})
        except Exception as e:
            return Response(
                {"message": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        invitation = self.get_object()
        
        if invitation.invited_email != request.user.email:
            raise PermissionDenied("Cette invitation ne vous est pas destinée")
            
        if invitation.status != 'pending':
            raise serializers.ValidationError("Cette invitation n'est plus valide")
            
        invitation.status = 'rejected'
        invitation.save()
        
        return Response({"message": "Invitation rejetée"})