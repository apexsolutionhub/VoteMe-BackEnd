from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competitions", "0004_competitioncriterion"),
    ]

    operations = [
        migrations.AddField(
            model_name="competitionvideo",
            name="title",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
