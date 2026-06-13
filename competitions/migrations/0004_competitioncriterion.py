from django.db import migrations, models
import django.db.models.deletion


def seed_criteria(apps, schema_editor):
    Competition = apps.get_model("competitions", "Competition")
    CompetitionCriterion = apps.get_model("competitions", "CompetitionCriterion")

    for competition in Competition.objects.all():
        if CompetitionCriterion.objects.filter(competition=competition).exists():
            continue

        milestones = [
            ("profile_complete", "Profile ready", "Complete your candidate profile.", 1, 10),
            ("video_count", "First video live", "Submit at least one competition video.", 1, 20),
            ("views", "100 views", "Reach 100 total video views.", 100, 30),
            ("likes", "50 likes", "Collect 50 likes across your videos.", 50, 40),
            ("brand_mentions", "Brand buzz", "Get a comment mentioning the brand.", 1, 50),
        ]
        for metric_key, title, description, target, sort_order in milestones:
            CompetitionCriterion.objects.create(
                competition=competition,
                kind="milestone",
                metric_key=metric_key,
                evaluation_mode="absolute",
                title=title,
                description=description,
                target_value=target,
                sort_order=sort_order,
            )

        weights = competition.scoring_weights or {}
        metric_defaults = [
            ("views", float(weights.get("views", 1))),
            ("likes", float(weights.get("likes", 3))),
            ("comments", float(weights.get("comments", 5))),
            ("shares", float(weights.get("shares", 2))),
            ("brand_mentions", float(weights.get("brand_mentions", 10))),
        ]
        for index, (metric_key, weight) in enumerate(metric_defaults, start=1):
            CompetitionCriterion.objects.create(
                competition=competition,
                kind="metric",
                metric_key=metric_key,
                evaluation_mode="absolute",
                title=metric_key.replace("_", " ").title(),
                description=f"Scoring weight for {metric_key.replace('_', ' ')}.",
                weight_value=weight,
                weight_input_type="number",
                weight_display=str(weight),
                sort_order=index * 10,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("competitions", "0003_replace_toxicity_with_brand_mentions"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompetitionCriterion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("milestone", "Milestone"), ("metric", "Scoring metric")], max_length=20)),
                ("metric_key", models.CharField(choices=[("views", "Views"), ("likes", "Likes"), ("comments", "Comments"), ("shares", "Shares"), ("brand_mentions", "Brand mentions"), ("video_count", "Video count"), ("profile_complete", "Profile complete"), ("engagement_score", "Engagement score"), ("rank", "Leaderboard rank")], max_length=40)),
                ("evaluation_mode", models.CharField(choices=[("absolute", "Fixed target"), ("relative", "Relative to field")], default="absolute", max_length=20)),
                ("title", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True, default="")),
                ("target_value", models.FloatField(blank=True, help_text="Fixed target for absolute milestones.", null=True)),
                ("weight_value", models.FloatField(default=0, help_text="Numeric weight or percentage value for scoring metrics.")),
                ("weight_input_type", models.CharField(choices=[("number", "Number"), ("percentage", "Percentage"), ("word", "Word")], default="number", max_length=20)),
                ("weight_display", models.CharField(blank=True, default="", help_text='Raw admin input such as "30%", "high", or "5".', max_length=40)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("competition", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="criteria", to="competitions.competition")),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.RunPython(seed_criteria, migrations.RunPython.noop),
    ]
