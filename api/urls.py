from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from .views import (
    ProjectViewSet,
    AnnotationViewSet,
    CommunityAnnotationViewSet,
    NotificationViewSet,
    AnnotationHistoryViewSet,
    detect_objects,
    MyTokenObtainPairView,
    register_user
)

router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'annotations', AnnotationViewSet, basename='annotation')
router.register(r'annotation-history', AnnotationHistoryViewSet, basename='annotation-history')
router.register(r'community-annotations', CommunityAnnotationViewSet, basename='community-annotation')
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    # Routes d'authentification
    path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('register/', register_user, name='register'),
    
    # Routes API
    path('', include(router.urls)),
    path('detect/', detect_objects, name='detect-objects'),
]
