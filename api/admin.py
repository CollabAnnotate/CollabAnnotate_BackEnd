from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CollabUserAdmin(UserAdmin):
    """Seul endroit où le rôle applicatif d'un utilisateur peut être modifié."""
    list_display = ('username', 'email', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('CollabAnnotate', {'fields': ('role', 'bio')}),
    )
