from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from django.urls import path
from .views import MyTokenObtainPairView  

from .views import (
    MyTokenObtainPairView, 
    UserListCreateView,
    ProjectListCreateView, 
    ProjectDetailView,
    DatasetListCreateView, 
    DatasetDetailView,
    register_user,
    upload_and_detect,
    save_annotations,
    get_annotations_for_review,
    validate_annotation
)

urlpatterns = [
    # Auth endpoints
    path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', register_user, name='register'),

    # User management
    path('users/', UserListCreateView.as_view(), name='user-list-create'),

    # Projects
    path('projects/', ProjectListCreateView.as_view(), name='project-list-create'),
    path('projects/<int:pk>/', ProjectDetailView.as_view(), name='project-detail'),

    # Datasets
    path('datasets/', DatasetListCreateView.as_view(), name='dataset-list-create'),
    path('datasets/<int:pk>/', DatasetDetailView.as_view(), name='dataset-detail'),

    # Annotations
    path('detect/', upload_and_detect, name='detect_objects'),
    path('annotations/', save_annotations, name='save_annotations'),
    path('annotations/review/', get_annotations_for_review, name='get_annotations_review'),
    path('annotations/<int:annotation_id>/validate/', validate_annotation, name='validate_annotation'),
]

