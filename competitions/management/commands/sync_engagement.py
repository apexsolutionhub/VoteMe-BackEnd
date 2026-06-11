from django.core.management.base import BaseCommand

from competitions.models import Competition
from competitions.sync import sync_competition_videos


class Command(BaseCommand):
    help = "Sync engagement metrics for all live competitions with tracking enabled."

    def handle(self, *args, **options):
        competitions = Competition.objects.filter(
            status=Competition.Status.LIVE,
            live_tracking_enabled=True,
        )
        total = 0
        for competition in competitions:
            synced = sync_competition_videos(competition)
            total += synced
            self.stdout.write(
                self.style.SUCCESS(
                    f"Synced {synced} videos for {competition.organization.slug}"
                )
            )

        self.stdout.write(self.style.SUCCESS(f"Done. {total} videos synced."))
