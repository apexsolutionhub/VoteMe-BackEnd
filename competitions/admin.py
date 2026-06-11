from django.contrib import admin

from .models import (
    CandidateProfile,
    Competition,
    CompetitionVideo,
    EngagementSnapshot,
    TikTokConnection,
    VideoComment,
)


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "social_platform", "status", "live_tracking_enabled")
    list_filter = ("status", "social_platform", "live_tracking_enabled")


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "follower_count", "is_profile_complete")
    list_filter = ("organization", "is_profile_complete")


@admin.register(CompetitionVideo)
class CompetitionVideoAdmin(admin.ModelAdmin):
    list_display = ("url", "competition", "candidate_profile", "engagement_score", "last_synced_at")
    list_filter = ("competition", "is_active")


@admin.register(EngagementSnapshot)
class EngagementSnapshotAdmin(admin.ModelAdmin):
    list_display = ("video", "engagement_score", "captured_at")


@admin.register(TikTokConnection)
class TikTokConnectionAdmin(admin.ModelAdmin):
    list_display = ("candidate_profile", "open_id", "connected_at")


@admin.register(VideoComment)
class VideoCommentAdmin(admin.ModelAdmin):
    list_display = ("video", "mentions_brand", "created_at")
    list_filter = ("mentions_brand",)
