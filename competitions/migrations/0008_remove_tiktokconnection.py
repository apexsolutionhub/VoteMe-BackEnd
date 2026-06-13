from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("competitions", "0007_comment_scoring_settings"),
    ]

    operations = [
        migrations.DeleteModel(
            name="TikTokConnection",
        ),
    ]
