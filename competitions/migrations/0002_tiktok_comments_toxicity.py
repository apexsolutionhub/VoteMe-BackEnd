import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competitions", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="competitionvideo",
            name="clean_comments",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="competitionvideo",
            name="toxic_comments",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="TikTokConnection",
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
                ("open_id", models.CharField(blank=True, default="", max_length=120)),
                ("access_token", models.TextField(blank=True, default="")),
                ("refresh_token", models.TextField(blank=True, default="")),
                ("access_token_expires_at", models.DateTimeField(blank=True, null=True)),
                ("refresh_token_expires_at", models.DateTimeField(blank=True, null=True)),
                ("scope", models.CharField(blank=True, default="", max_length=255)),
                ("connected_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "candidate_profile",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tiktok_connection",
                        to="competitions.candidateprofile",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="VideoComment",
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
                ("platform_comment_id", models.CharField(max_length=120)),
                ("text", models.TextField()),
                ("is_toxic", models.BooleanField(blank=True, null=True)),
                ("toxicity_score", models.FloatField(blank=True, null=True)),
                ("toxicity_categories", models.JSONField(blank=True, default=dict)),
                ("moderated_at", models.DateTimeField(blank=True, null=True)),
                ("platform_created_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "video",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="video_comments",
                        to="competitions.competitionvideo",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("video", "platform_comment_id")},
            },
        ),
    ]
