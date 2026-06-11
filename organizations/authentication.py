from rest_framework_simplejwt.authentication import JWTAuthentication

from organizations.models import OrganizationMember


def load_tenant_for_user(user, auth) -> tuple:
    if user is None or not user.is_authenticated:
        return None, None

    org_id = auth.get("organization_id") if auth else None
    if not org_id:
        return None, None

    membership = (
        OrganizationMember.objects.filter(
            user=user,
            organization_id=org_id,
            is_active=True,
        )
        .select_related("organization")
        .first()
    )
    if membership is None:
        return None, None

    return membership.organization, membership


class TenantJWTAuthentication(JWTAuthentication):
    """Attach organization + membership after JWT validation (middleware runs too early)."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result
        request.organization, request.membership = load_tenant_for_user(
            user, validated_token
        )
        return user, validated_token
