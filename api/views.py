import os
import secrets
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

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
)
from .permissions import (
    AnnotationPermission,
    CollaboratorPermission,
    CommunityAnnotationPermission,
    DataItemPermission,
    DatasetPermission,
    IsRoleAdmin,
    ProjectPermission,
    has_project_role,
    visible_projects_q,
)
from .serializers import (
    AdminUserSerializer,
    AnnotationHistorySerializer,
    AnnotationSerializer,
    CommunityAnnotationSerializer,
    DataItemSerializer,
    DatasetSerializer,
    NotificationSerializer,
    ProjectCollaboratorSerializer,
    ProjectInvitationSerializer,
    ProjectSerializer,
    UserSerializer,
)

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
    # Création : DatasetSerializer.validate_project ; modification : DatasetPermission
    permission_classes = [permissions.IsAuthenticated, DatasetPermission]
    queryset = Dataset.objects.all()

    def get_queryset(self):
        """Mêmes règles de visibilité que les projets."""
        return Dataset.objects.filter(
            visible_projects_q(self.request.user, prefix='project__')
        ).distinct()

class DataItemViewSet(viewsets.ModelViewSet):
    serializer_class = DataItemSerializer
    # Création : DataItemSerializer.validate_dataset ; modification : DataItemPermission
    permission_classes = [permissions.IsAuthenticated, DataItemPermission]
    queryset = DataItem.objects.all()

    def get_queryset(self):
        return DataItem.objects.filter(
            visible_projects_q(self.request.user, prefix='dataset__project__')
        ).distinct()

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
    # Pas de try/except global : un refus de permission (validate_dataitem) doit
    # rester un 403, pas devenir une 500.
    saved_annotations = []
    for ann in request.data.get('annotations', []):
        serializer = AnnotationSerializer(data={
            'dataitem': ann.get('dataitem_id'),
            'label': ann.get('label'),
            'x_min': ann.get('x_min'),
            'y_min': ann.get('y_min'),
            'x_max': ann.get('x_max'),
            'y_max': ann.get('y_max'),
            'confidence': ann.get('confidence')
        }, context={'request': request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        saved_annotations.append(serializer.data)

    return Response(saved_annotations, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_annotations_for_review(request):
    user = request.user
    if user.role not in ['verificateur', 'admin']:
        return Response({"error": "Permission refusée"}, status=403)

    annotations = (
        Annotation.objects.filter(is_validated=False)
        .select_related('dataitem', 'created_by')
        .order_by('created_at')
    )
    serializer = AnnotationSerializer(annotations, many=True, context={'request': request})
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_annotation(request, annotation_id):
    user = request.user
    if user.role not in ['verificateur', 'admin']:
        return Response({"error": "Permission refusée"}, status=403)

    try:
        annotation = Annotation.objects.get(id=annotation_id)
    except Annotation.DoesNotExist:
        return Response({"error": "Annotation non trouvée"}, status=status.HTTP_404_NOT_FOUND)

    # Ne pas nommer cette variable `status` : elle masquerait le module rest_framework.status
    validation_status = request.data.get('status')
    if validation_status not in ['validé', 'rejeté']:
        return Response({"error": "Statut invalide"}, status=status.HTTP_400_BAD_REQUEST)

    annotation.is_validated = True
    annotation.validation_status = validation_status
    annotation.validation_comment = request.data.get('comment', '')
    annotation.validated_by = user
    annotation.validated_at = timezone.now()
    annotation.save()

    return Response({"message": "Annotation mise à jour avec succès"})

class AnnotationViewSet(viewsets.ModelViewSet):
    serializer_class = AnnotationSerializer
    # Création : AnnotationSerializer.validate_dataitem ; modification : AnnotationPermission
    permission_classes = [permissions.IsAuthenticated, AnnotationPermission]
    queryset = Annotation.objects.all()

    def get_queryset(self):
        """Annotations des projets visibles, y compris ceux où l'on collabore."""
        dataitem_id = self.request.query_params.get('dataitem', None)
        queryset = Annotation.objects.filter(
            visible_projects_q(self.request.user, prefix='dataitem__dataset__project__')
        ).distinct()

        if dataitem_id:
            queryset = queryset.filter(dataitem_id=dataitem_id)

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        # L'historique est écrit par Annotation.save() : ne pas le dupliquer ici
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

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        annotation = self.get_object()
        # Seules les modifications conservent un état précédent (l'entrée « create » est vide)
        history = (
            AnnotationHistory.objects.filter(annotation=annotation, modification_type='update')
            .order_by('-modified_at')
            .first()
        )
        if history is None:
            return Response({"error": "Aucune version précédente à restaurer"},
                            status=status.HTTP_404_NOT_FOUND)

        annotation.last_modified_by = request.user
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
        # Uniquement l'historique des projets visibles (auparavant : tout l'historique)
        queryset = super().get_queryset().filter(
            visible_projects_q(self.request.user, prefix='annotation__dataitem__dataset__project__')
        ).distinct()

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
        visible_ids = Project.objects.filter(visible_projects_q(self.request.user)).values('id')
        # Compteurs calculés en SQL (GROUP BY) pour tous les projets d'un coup,
        # plutôt qu'une requête par projet (problème N+1)
        return (
            Project.objects.filter(id__in=visible_ids)
            .select_related('created_by')
            .annotate(
                total_images=models.Count('dataset__dataitem', distinct=True),
                total_annotations=models.Count('dataset__dataitem__annotation', distinct=True),
                pending_annotations=models.Count(
                    'dataset__dataitem__annotation',
                    filter=Q(dataset__dataitem__annotation__is_validated=False),
                    distinct=True,
                ),
            )
            .order_by('-created_at')
        )

    def perform_create(self, serializer):
        project = serializer.save(created_by=self.request.user)
        # « Public » à la création = publié (visibility/status sont en lecture seule)
        if self.request.data.get('visibility') == 'public':
            project.publish()

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
        dataitems = DataItem.objects.filter(dataset__project=project)
        annotations = Annotation.objects.filter(dataitem__dataset__project=project)
        collaborators = ProjectCollaborator.objects.filter(project=project)

        total_images = dataitems.count()
        accepted = annotations.filter(validation_status='validé').count()
        rejected = annotations.filter(validation_status='rejeté').count()
        pending = annotations.filter(is_validated=False).count()
        annotated_images = dataitems.filter(annotation__isnull=False).distinct().count()
        avg_confidence = annotations.aggregate(avg=models.Avg('confidence'))['avg']

        stats = {
            'total_images': total_images,
            'total_annotations': annotations.count(),
            'pending_annotations': pending,
            'total_collaborators': collaborators.count() + 1,  # +1 pour inclure le créateur
            'validated_annotations': annotations.filter(is_validated=True).count(),
            'rejected_annotations': rejected,
            # Données prêtes pour les graphiques de l'écran Rapports
            'annotations_by_label': [
                {'name': row['label'], 'value': row['count']}
                for row in annotations.values('label')
                .annotate(count=models.Count('id'))
                .order_by('-count')
            ],
            'validation_breakdown': [
                {'name': 'Validées', 'value': accepted},
                {'name': 'Rejetées', 'value': rejected},
                {'name': 'En attente', 'value': pending},
            ],
            # Indicateurs mesurables sans vérité terrain (None si pas encore de données)
            'quality': {
                'acceptance_rate': accepted / (accepted + rejected) if accepted + rejected else None,
                'average_confidence': avg_confidence,
                'completion_rate': annotated_images / total_images if total_images else None,
            },
        }

        return Response(stats)

    @action(detail=True, methods=['POST'])
    def publish(self, request, pk=None):
        # Réservé au propriétaire : contrôlé par ProjectPermission dans get_object()
        project = self.get_object()
        project.publish()  # met aussi à jour visibility et published_at
        return Response({'status': 'published'})

    @action(detail=True, methods=['POST'])
    def unpublish(self, request, pk=None):
        project = self.get_object()
        project.unpublish()
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
    permission_classes = [permissions.IsAuthenticated, CommunityAnnotationPermission]
    queryset = CommunityAnnotation.objects.all()

    def get_queryset(self):
        return CommunityAnnotation.objects.filter(
            dataitem__dataset__project__visibility='public'
        )

    def perform_create(self, serializer):
        dataitem = serializer.validated_data['dataitem']
        project = dataitem.dataset.project

        if project.visibility != 'public' or not project.allow_community_annotations:
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

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """Les notifications sont créées par le système : l'utilisateur ne fait que les lire."""
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

        # Mêmes règles de robustesse que partout ailleurs (AUTH_PASSWORD_VALIDATORS)
        try:
            validate_password(new_password, user)
        except DjangoValidationError as e:
            return Response({'error': ' '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        return Response({'message': 'Mot de passe modifié avec succès'})


class AdminUserViewSet(viewsets.ModelViewSet):
    """Gestion des comptes par les administrateurs (écran Utilisateurs)."""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, IsRoleAdmin]
    queryset = User.objects.all().order_by('username')

    def perform_update(self, serializer):
        # Garde-fou : un admin ne peut pas se retirer ses propres droits
        if serializer.instance == self.request.user:
            data = serializer.validated_data
            if data.get('role', 'admin') != 'admin' or data.get('is_active') is False:
                raise serializers.ValidationError(
                    "Vous ne pouvez pas retirer vos propres droits d'administrateur."
                )
        serializer.save()

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise serializers.ValidationError("Vous ne pouvez pas supprimer votre propre compte.")
        instance.delete()

class ProjectCollaboratorViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectCollaboratorSerializer
    permission_classes = [permissions.IsAuthenticated, CollaboratorPermission]

    def get_queryset(self):
        """L'équipe des projets dont on est propriétaire ou membre, filtrable par ?project=."""
        user = self.request.user
        queryset = ProjectCollaborator.objects.filter(
            Q(project__created_by=user) | Q(project__collaborators__user=user)
        ).select_related('user', 'project').distinct()

        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def perform_create(self, serializer):
        project = serializer.validated_data['project']
        if not has_project_role(self.request.user, project, ('admin',)):
            raise PermissionDenied("Seuls le propriétaire et les administrateurs du projet ajoutent des collaborateurs")
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
        # Pas de try/except global : DRF renvoie lui-même 400 (ValidationError)
        # et 403 (PermissionDenied) ; les intercepter les transformait en 500.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        project = serializer.validated_data['project']

        # Seuls le créateur du projet et ses collaborateurs admin invitent
        is_creator = project.created_by == request.user
        is_admin = ProjectCollaborator.objects.filter(
            project=project,
            user=request.user,
            role='admin'
        ).exists()
        if not (is_creator or is_admin):
            raise PermissionDenied("Vous n'avez pas la permission d'inviter des collaborateurs sur ce projet")

        invitation = serializer.save(
            invited_by=request.user,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(days=7),
            status='pending'
        )

        # Notifier l'utilisateur invité s'il a déjà un compte
        invited_user = get_user_model().objects.filter(email=invitation.invited_email).first()
        if invited_user:
            Notification.objects.create(
                user=invited_user,
                notification_type='project_invitation',
                content=f"Vous avez été invité à collaborer sur le projet {project.name}",
                related_project=project
            )

        return Response(serializer.data, status=status.HTTP_201_CREATED)

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
