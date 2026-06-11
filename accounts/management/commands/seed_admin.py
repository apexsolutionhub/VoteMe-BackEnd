from django.core.management.base import BaseCommand

from accounts.models import User
from competitions.models import Competition
from organizations.models import Organization, OrganizationMember


class Command(BaseCommand):
    help = "Create the default admin user and demo organization (ellaVote)"

    def handle(self, *args, **options):
        username = "ellaVote"
        password = "12345678"
        org_slug = "ella-vote"

        organization, org_created = Organization.objects.get_or_create(
            slug=org_slug,
            defaults={"name": "Ella Vote Demo"},
        )
        Organization.objects.filter(pk=organization.pk).update(
            logo_url="/orgs/ella-vote.jpg",
        )
        organization.refresh_from_db()

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "role": User.Role.ADMIN,
                "must_change_password": False,
                "is_staff": True,
                "is_superuser": True,
                "first_name": "Ella",
                "last_name": "Admin",
            },
        )

        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"Admin user '{username}' created.")
            )
        else:
            user.role = User.Role.ADMIN
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.WARNING(
                    f"Admin user '{username}' already existed — password reset."
                )
            )

        OrganizationMember.objects.get_or_create(
            organization=organization,
            user=user,
            defaults={"role": OrganizationMember.Role.OWNER},
        )

        Competition.objects.get_or_create(
            organization=organization,
            defaults={
                "title": "Ella Vote TikTok Competition",
                "social_platform": Competition.SocialPlatform.TIKTOK,
                "registration_criteria": (
                    "Complete profile and submit TikTok competition videos."
                ),
                "scoring_criteria": (
                    "Weighted views, likes, comments, and shares."
                ),
                "final_award": "Top creator wins the engagement cup.",
                "scoring_weights": {
                    "views": 1,
                    "likes": 3,
                    "comments": 5,
                    "shares": 2,
                },
            },
        )

        if org_created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Organization '{organization.slug}' created. "
                    f"Login with organization URL: {org_slug}"
                )
            )
