from .models import OrganizationMember


def _load_tenant(request, user=None):
    user = user if user is not None else request.user
    if not getattr(user, "is_authenticated", False):
        return None, None

    auth = getattr(request, "auth", None)
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


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization, request.membership = _load_tenant(request)
        return self.get_response(request)
