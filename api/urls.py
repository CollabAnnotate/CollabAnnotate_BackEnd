from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenVerifyView
from .views import (
    ProjectViewSet,
    AnnotationViewSet,
    CommunityAnnotationViewSet,
    NotificationViewSet,
    AnnotationHistoryViewSet,
    detect_objects,
    MyTokenObtainPairView,
    CookieTokenRefreshView,
    LogoutView,
    register_user,
    UserViewSet,
    DatasetViewSet,
    DataItemViewSet,
    upload_and_detect,
    save_annotations,
    get_annotations_for_review,
    validate_annotation,
    ProjectCollaboratorViewSet,
    ProjectInvitationViewSet
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'datasets', DatasetViewSet, basename='dataset')
router.register(r'dataitems', DataItemViewSet, basename='dataitem')
router.register(r'annotations', AnnotationViewSet, basename='annotation')
router.register(r'annotation-history', AnnotationHistoryViewSet, basename='annotation-history')
router.register(r'community-annotations', CommunityAnnotationViewSet, basename='community-annotation')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'project-collaborators', ProjectCollaboratorViewSet, basename='project-collaborator')
router.register(r'project-invitations', ProjectInvitationViewSet, basename='project-invitation')

urlpatterns = [
    # Routes d'authentification
    path('register/', register_user, name='register'),
    path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('token/logout/', LogoutView.as_view(), name='token_logout'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # Routes API
    path('', include(router.urls)),
    path('detect/', detect_objects, name='detect-objects'),
    path('upload-and-detect/', upload_and_detect, name='upload_and_detect'),
    path('detect-objects/', detect_objects, name='detect_objects'),
    path('save-annotations/', save_annotations, name='save_annotations'),
    path('annotations/review/', get_annotations_for_review, name='get_annotations_for_review'),
    path('annotations/<int:annotation_id>/validate/', validate_annotation, name='validate_annotation'),
]
