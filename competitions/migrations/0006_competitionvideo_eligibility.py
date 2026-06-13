from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competitions", "0005_competitionvideo_title"),
    ]

    operations = [
        migrations.AddField(
            model_name="competitionvideo",
            name="platform_published_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the video was published on the social platform.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="competitionvideo",
            name="is_competition_eligible",
            field=models.BooleanField(
                default=False,
                help_text="True when published within the competition live window.",
            ),
        ),
        migrations.AddField(
            model_name="competitionvideo",
            name="ineligibility_reason",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
    ]
