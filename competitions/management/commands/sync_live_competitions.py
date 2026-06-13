from django.core.management.base import BaseCommand

from competitions.models import Competition
from competitions.sync import sync_competition_videos


class Command(BaseCommand):
    help = "Sync metrics for all competitions with live tracking enabled."

    def handle(self, *args, **options):
        competitions = Competition.objects.filter(live_tracking_enabled=True)
        total = 0
        for competition in competitions:
            result = sync_competition_videos(competition)
            synced = result["synced_count"]
            total += synced
            self.stdout.write(
                f"{competition.organization.slug}: synced {synced} video(s)"
            )
        self.stdout.write(self.style.SUCCESS(f"Done — {total} video(s) updated."))
