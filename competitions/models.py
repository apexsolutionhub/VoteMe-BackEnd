from django.conf import settings
from django.db import models

from organizations.models import Organization


class Competition(models.Model):
    class SocialPlatform(models.TextChoices):
        TIKTOK = "tiktok", "TikTok"
        YOUTUBE = "youtube", "YouTube"
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK = "facebook", "Facebook"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        LIVE = "live", "Live"
        ENDED = "ended", "Ended"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="competitions",
    )
    title = models.CharField(max_length=200, default="Social Media Engagement Competition")
    description = models.TextField(blank=True, default="")
    social_platform = models.CharField(
        max_length=20,
        choices=SocialPlatform.choices,
        default=SocialPlatform.TIKTOK,
    )
    registration_criteria = models.TextField(
        blank=True,
        default="",
        help_text="Requirements candidates must meet to join.",
    )
    scoring_criteria = models.TextField(
        blank=True,
        default="",
        help_text="How engagement is scored and ranked.",
    )
    final_award = models.TextField(
        blank=True,
        default="",
        help_text="Prize or recognition for winners.",
    )
    scoring_weights = models.JSONField(
        default=dict,
        blank=True,
        help_text='Weights e.g. {"views": 1, "likes": 3, "comments": 5, "shares": 2}',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    live_tracking_enabled = models.BooleanField(default=True)
    tracking_interval_minutes = models.PositiveSmallIntegerField(default=10)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.organization.slug})"

    def get_scoring_weights(self) -> dict[str, float]:
        defaults = {
            "views": 1.0,
            "likes": 3.0,
            "comments": 5.0,
            "shares": 2.0,
            "brand_mentions": 10.0,
        }
        if not self.scoring_weights:
            return defaults
        merged = defaults.copy()
        for key, value in self.scoring_weights.items():
            try:
                merged[key] = float(value)
            except (TypeError, ValueError):
                continue
        return merged


class CandidateProfile(models.Model):
    class Sex(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="candidate_profiles",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="candidate_profiles",
    )
    sex = models.CharField(
        max_length=20,
        choices=Sex.choices,
        blank=True,
        default="",
    )
    social_channel_url = models.URLField(blank=True, default="")
    follower_count = models.PositiveIntegerField(default=0)
    profile_image_url = models.URLField(blank=True, default="")
    is_profile_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "organization")
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.user.username} ({self.organization.slug})"


class CompetitionVideo(models.Model):
    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name="videos",
    )
    candidate_profile = models.ForeignKey(
        CandidateProfile,
        on_delete=models.CASCADE,
        related_name="videos",
    )
    url = models.URLField()
    platform_video_id = models.CharField(max_length=120, blank=True, default="")
    views = models.BigIntegerField(default=0)
    likes = models.BigIntegerField(default=0)
    comments = models.BigIntegerField(default=0)
    shares = models.BigIntegerField(default=0)
    brand_mention_comments = models.PositiveIntegerField(default=0)
    engagement_score = models.FloatField(default=0)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-engagement_score", "-updated_at"]
        unique_together = ("competition", "url")

    def __str__(self) -> str:
        return self.url


class TikTokConnection(models.Model):
    candidate_profile = models.OneToOneField(
        CandidateProfile,
        on_delete=models.CASCADE,
        related_name="tiktok_connection",
    )
    open_id = models.CharField(max_length=120, blank=True, default="")
    access_token = models.TextField(blank=True, default="")
    refresh_token = models.TextField(blank=True, default="")
    access_token_expires_at = models.DateTimeField(null=True, blank=True)
    refresh_token_expires_at = models.DateTimeField(null=True, blank=True)
    scope = models.CharField(max_length=255, blank=True, default="")
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"TikTok @ {self.candidate_profile}"


class VideoComment(models.Model):
    video = models.ForeignKey(
        CompetitionVideo,
        on_delete=models.CASCADE,
        related_name="video_comments",
    )
    platform_comment_id = models.CharField(max_length=120)
    text = models.TextField()
    mentions_brand = models.BooleanField(default=False)
    platform_created_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("video", "platform_comment_id")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.text[:60]


class EngagementSnapshot(models.Model):
    video = models.ForeignKey(
        CompetitionVideo,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    views = models.BigIntegerField(default=0)
    likes = models.BigIntegerField(default=0)
    comments = models.BigIntegerField(default=0)
    shares = models.BigIntegerField(default=0)
    engagement_score = models.FloatField(default=0)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-captured_at"]
