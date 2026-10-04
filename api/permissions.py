from django.db.models import Q
from rest_framework.permissions import BasePermission, SAFE_METHODS

# Rôles de collaborateur (ProjectCollaborator.role) autorisés par type d'action
EDITOR_ROLES = ('editor', 'admin')
ANNOTATOR_ROLES = ('annotator', 'editor', 'admin')

# Actions réservées au propriétaire du projet
OWNER_ONLY_ACTIONS = ('destroy', 'publish', 'unpublish')
# Actions ouvertes aux collaborateurs qui annotent
ANNOTATOR_ACTIONS = ('detect_objects',)


def visible_projects_q(user, prefix=''):
    """
    Filtre des projets visibles par l'utilisateur : les siens, ceux où il collabore,
    et les projets publiés. `prefix` permet de l'appliquer depuis un modèle lié,
    par exemple prefix='project__' pour filtrer des Dataset.
    """
    return (
        Q(**{f'{prefix}created_by': user}) |
        Q(**{f'{prefix}collaborators__user': user}) |
        Q(**{f'{prefix}status': 'published'})
    )


def has_project_role(user, project, roles):
    """Vrai si l'utilisateur est propriétaire du projet ou collaborateur avec l'un des rôles."""
    if project.created_by_id == user.id:
        return True
    return project.collaborators.filter(user=user, role__in=roles).exists()


class ProjectPermission(BasePermission):
    """
    Droits sur un projet, évalués objet par objet (équivalent d'un Voter Symfony) :
    - lecture : tout projet visible (voir ProjectViewSet.get_queryset) ;
    - suppression, publication : propriétaire uniquement ;
    - détection d'objets : propriétaire ou collaborateur annotateur/éditeur/admin ;
    - autres modifications : propriétaire ou collaborateur éditeur/admin.
    """
    message = "Vous n'avez pas les droits nécessaires sur ce projet."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if view.action in OWNER_ONLY_ACTIONS:
            return obj.created_by_id == request.user.id
        if view.action in ANNOTATOR_ACTIONS:
            return has_project_role(request.user, obj, ANNOTATOR_ROLES)
        return has_project_role(request.user, obj, EDITOR_ROLES)


class IsRoleAdmin(BasePermission):
    """Réservé aux utilisateurs dont le rôle applicatif est 'admin'."""
    message = 'Réservé aux administrateurs.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'admin')


class DatasetPermission(BasePermission):
    """Un dataset se lit comme son projet et se modifie avec les droits d'éditeur du projet."""
    message = "Vous n'avez pas les droits nécessaires sur ce projet."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return has_project_role(request.user, obj.project, EDITOR_ROLES)
