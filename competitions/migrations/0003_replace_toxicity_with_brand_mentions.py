from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competitions", "0002_tiktok_comments_toxicity"),
    ]

    operations = [
        migrations.AddField(
            model_name="competitionvideo",
            name="brand_mention_comments",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="videocomment",
            name="mentions_brand",
            field=models.BooleanField(default=False),
        ),
        migrations.RemoveField(
            model_name="competitionvideo",
            name="clean_comments",
        ),
        migrations.RemoveField(
            model_name="competitionvideo",
            name="toxic_comments",
        ),
        migrations.RemoveField(
            model_name="videocomment",
            name="is_toxic",
        ),
        migrations.RemoveField(
            model_name="videocomment",
            name="toxicity_score",
        ),
        migrations.RemoveField(
            model_name="videocomment",
            name="toxicity_categories",
        ),
        migrations.RemoveField(
            model_name="videocomment",
            name="moderated_at",
        ),
    ]
