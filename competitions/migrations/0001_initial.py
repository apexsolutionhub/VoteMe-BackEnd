import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("organizations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Competition",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        default="Social Media Engagement Competition",
                        max_length=200,
                    ),
                ),
                ("description", models.TextField(blank=True, default="")),
                (
                    "social_platform",
                    models.CharField(
                        choices=[
                            ("tiktok", "TikTok"),
                            ("youtube", "YouTube"),
                            ("instagram", "Instagram"),
                            ("facebook", "Facebook"),
                        ],
                        default="tiktok",
                        max_length=20,
                    ),
                ),
                (
                    "registration_criteria",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Requirements candidates must meet to join.",
                    ),
                ),
                (
                    "scoring_criteria",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="How engagement is scored and ranked.",
                    ),
                ),
                (
                    "final_award",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Prize or recognition for winners.",
                    ),
                ),
                (
                    "scoring_weights",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='Weights e.g. {"views": 1, "likes": 3, "comments": 5, "shares": 2}',
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("live", "Live"),
                            ("ended", "Ended"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("live_tracking_enabled", models.BooleanField(default=True)),
                ("tracking_interval_minutes", models.PositiveSmallIntegerField(default=10)),
                ("start_at", models.DateTimeField(blank=True, null=True)),
                ("end_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="competitions",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CandidateProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "sex",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("male", "Male"),
                            ("female", "Female"),
                            ("other", "Other"),
                            ("prefer_not_to_say", "Prefer not to say"),
                        ],
                        default="",
                        max_length=20,
                    ),
                ),
                ("social_channel_url", models.URLField(blank=True, default="")),
                ("follower_count", models.PositiveIntegerField(default=0)),
                ("profile_image_url", models.URLField(blank=True, default="")),
                ("is_profile_complete", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="candidate_profiles",
                        to="organizations.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="candidate_profiles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
                "unique_together": {("user", "organization")},
            },
        ),
        migrations.CreateModel(
            name="CompetitionVideo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("url", models.URLField()),
                (
                    "platform_video_id",
                    models.CharField(blank=True, default="", max_length=120),
                ),
                ("views", models.BigIntegerField(default=0)),
                ("likes", models.BigIntegerField(default=0)),
                ("comments", models.BigIntegerField(default=0)),
                ("shares", models.BigIntegerField(default=0)),
                ("engagement_score", models.FloatField(default=0)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "candidate_profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="videos",
                        to="competitions.candidateprofile",
                    ),
                ),
                (
                    "competition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="videos",
                        to="competitions.competition",
                    ),
                ),
            ],
            options={
                "ordering": ["-engagement_score", "-updated_at"],
                "unique_together": {("competition", "url")},
            },
        ),
        migrations.CreateModel(
            name="EngagementSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("views", models.BigIntegerField(default=0)),
                ("likes", models.BigIntegerField(default=0)),
                ("comments", models.BigIntegerField(default=0)),
                ("shares", models.BigIntegerField(default=0)),
                ("engagement_score", models.FloatField(default=0)),
                ("captured_at", models.DateTimeField(auto_now_add=True)),
                (
                    "video",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="snapshots",
                        to="competitions.competitionvideo",
                    ),
                ),
            ],
            options={
                "ordering": ["-captured_at"],
            },
        ),
    ]
