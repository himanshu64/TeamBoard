from rest_framework.permissions import BasePermission

from .models import Company


class IsAdminUser(BasePermission):
    message = 'Admin access required.'

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        try:
            return user.company.role == Company.Role.ADMIN
        except Company.DoesNotExist:
            return False
