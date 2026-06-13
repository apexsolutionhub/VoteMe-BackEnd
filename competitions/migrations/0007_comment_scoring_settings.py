from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competitions", "0006_competitionvideo_eligibility"),
    ]

    operations = [
        migrations.AddField(
            model_name="competition",
            name="comment_scoring_mode",
            field=models.CharField(
                choices=[
                    ("all", "All comments"),
                    ("matched", "Matching comments only"),
                ],
                default="all",
                help_text="Whether comment scoring uses every comment or only matched ones.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="competition",
            name="comment_match_terms",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Optional triggers such as ["@ellaresort", "#ellaresort"].',
            ),
        ),
        migrations.AddField(
            model_name="competitionvideo",
            name="scored_comments",
            field=models.BigIntegerField(
                default=0,
                help_text="Comments that count toward competition scoring.",
            ),
        ),
    ]
