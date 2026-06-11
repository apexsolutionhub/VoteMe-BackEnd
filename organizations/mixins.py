from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from .models import Organization, OrganizationMember


class TenantViewMixin:
    def get_organization(self) -> Organization:
        organization = getattr(self.request, "organization", None)
        if organization is None:
            raise PermissionDenied("Organization context is required.")
        return organization

    def get_membership(self) -> OrganizationMember:
        membership = getattr(self.request, "membership", None)
        if membership is None:
            raise PermissionDenied("Organization membership is required.")
        return membership


def resolve_membership(user, organization_slug: str | None = None) -> tuple[Organization, OrganizationMember]:
    memberships = (
        OrganizationMember.objects.filter(user=user, is_active=True)
        .select_related("organization")
        .order_by("joined_at")
    )

    if organization_slug:
        membership = memberships.filter(organization__slug=organization_slug).first()
        if membership is None:
            raise PermissionDenied(
                detail="You do not have access to this organization."
            )
        return membership.organization, membership

    if memberships.count() == 1:
        membership = memberships.first()
        assert membership is not None
        return membership.organization, membership

    raise PermissionDenied(
        detail="This account belongs to multiple organizations. Contact your administrator."
    )
