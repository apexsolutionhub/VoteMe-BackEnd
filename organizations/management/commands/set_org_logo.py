from django.core.management.base import BaseCommand

from organizations.models import Organization


class Command(BaseCommand):
    help = "Set the public logo URL for an organization (e.g. /orgs/ella-vote.jpg)"

    def add_arguments(self, parser):
        parser.add_argument("slug", type=str, help="Organization slug")
        parser.add_argument("logo_url", type=str, help="Logo URL or site path")

    def handle(self, *args, **options):
        slug = options["slug"]
        logo_url = options["logo_url"]

        updated = Organization.objects.filter(slug=slug).update(logo_url=logo_url)
        if not updated:
            self.stderr.write(self.style.ERROR(f"No organization found with slug '{slug}'."))
            return

        self.stdout.write(
            self.style.SUCCESS(f"Set logo for '{slug}' to {logo_url}")
        )
