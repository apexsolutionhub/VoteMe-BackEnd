from rest_framework.permissions import BasePermission

from .models import OrganizationMember


class IsOrgAdmin(BasePermission):
    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        return membership is not None and membership.is_org_admin


class IsOrgCandidate(BasePermission):
    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        return (
            membership is not None
            and membership.role == OrganizationMember.Role.CANDIDATE
        )
