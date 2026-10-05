from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenVerifyView

from .views import (
    AdminUserViewSet,
    AnnotationHistoryViewSet,
    AnnotationViewSet,
    CommunityAnnotationViewSet,
    CookieTokenRefreshView,
    DataItemViewSet,
    DatasetViewSet,
    LogoutView,
    MyTokenObtainPairView,
    NotificationViewSet,
    ProjectCollaboratorViewSet,
    ProjectInvitationViewSet,
    ProjectViewSet,
    UserViewSet,
    detect_objects,
    get_annotations_for_review,
    register_user,
    save_annotations,
    upload_and_detect,
    validate_annotation,
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'admin/users', AdminUserViewSet, basename='admin-user')
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

    # Routes spécifiques AVANT le router : Django s'arrête à la première route qui
    # correspond, et 'annotations/<pk>/' du router capturerait 'review' comme pk.
    path('annotations/review/', get_annotations_for_review, name='get_annotations_for_review'),
    path('annotations/<int:annotation_id>/validate/', validate_annotation, name='validate_annotation'),

    # Routes API
    path('', include(router.urls)),
    path('detect/', detect_objects, name='detect-objects'),
    path('upload-and-detect/', upload_and_detect, name='upload_and_detect'),
    path('detect-objects/', detect_objects, name='detect_objects'),
    path('save-annotations/', save_annotations, name='save_annotations'),
]
