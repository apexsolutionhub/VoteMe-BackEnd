from django.core.management.base import BaseCommand

from accounts.models import User
from competitions.models import Competition
from organizations.models import Organization, OrganizationMember


class Command(BaseCommand):
    help = "Ensure demo admin/candidate accounts exist for organization ella-vote"

    def handle(self, *args, **options):
        from competitions.models import CandidateProfile

        org_slug = "ella-vote"
        password = "12345678"

        organization, _ = Organization.objects.get_or_create(
            slug=org_slug,
            defaults={"name": "Ella Vote Demo"},
        )
        Organization.objects.filter(pk=organization.pk).update(
            logo_url="/orgs/ella-vote.jpg",
        )
        organization.refresh_from_db()

        Competition.objects.get_or_create(
            organization=organization,
            defaults={
                "title": "Ella Vote TikTok Competition",
                "social_platform": Competition.SocialPlatform.TIKTOK,
            },
        )

        admin_user, admin_created = User.objects.get_or_create(
            username="ellaVote",
            defaults={
                "role": User.Role.ADMIN,
                "must_change_password": False,
                "is_staff": True,
                "is_superuser": True,
                "first_name": "Ella",
                "last_name": "Admin",
            },
        )
        admin_user.role = User.Role.ADMIN
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.is_active = True
        admin_user.set_password(password)
        admin_user.save()

        OrganizationMember.objects.update_or_create(
            organization=organization,
            user=admin_user,
            defaults={"role": OrganizationMember.Role.OWNER, "is_active": True},
        )

        candidate_user, candidate_created = User.objects.get_or_create(
            username="ellaCandidate",
            defaults={
                "role": User.Role.CANDIDATE,
                "must_change_password": False,
                "first_name": "Ella",
                "last_name": "Creator",
                "phone_number": "+10000000000",
            },
        )
        candidate_user.role = User.Role.CANDIDATE
        candidate_user.is_active = True
        candidate_user.must_change_password = False
        candidate_user.set_password(password)
        candidate_user.save()

        OrganizationMember.objects.update_or_create(
            organization=organization,
            user=candidate_user,
            defaults={"role": OrganizationMember.Role.CANDIDATE, "is_active": True},
        )

        CandidateProfile.objects.get_or_create(
            user=candidate_user,
            organization=organization,
        )

        self.stdout.write(self.style.SUCCESS("Demo accounts repaired successfully."))
        self.stdout.write(f"  Organization URL: {org_slug}")
        self.stdout.write("")
        self.stdout.write("  Admin portal (/Admin):")
        self.stdout.write("    Username: ellaVote")
        self.stdout.write(f"    Password: {password}")
        self.stdout.write(f"    Created:  {admin_created}")
        self.stdout.write("")
        self.stdout.write("  Candidate portal (/Candidates):")
        self.stdout.write("    Username: ellaCandidate")
        self.stdout.write(f"    Password: {password}")
        self.stdout.write(f"    Created:  {candidate_created}")
