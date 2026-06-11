from rest_framework_simplejwt.tokens import RefreshToken

from organizations.models import OrganizationMember


def tokens_for_membership(user, membership: OrganizationMember) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["organization_id"] = str(membership.organization_id)
    refresh["organization_slug"] = membership.organization.slug
    refresh["membership_role"] = membership.role
    refresh["user_role"] = user.role

    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }
