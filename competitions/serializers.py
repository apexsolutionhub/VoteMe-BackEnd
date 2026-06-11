from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.models import User
from accounts.serializers import UserSerializer
from competitions.models import CandidateProfile, Competition, CompetitionVideo
from competitions.validators import (
    extract_video_id,
    validate_competition_video_url,
    validate_social_channel_url,
)
from organizations.models import OrganizationMember


class CompetitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Competition
        fields = (
            "id",
            "title",
            "description",
            "social_platform",
            "registration_criteria",
            "scoring_criteria",
            "final_award",
            "scoring_weights",
            "status",
            "live_tracking_enabled",
            "tracking_interval_minutes",
            "start_at",
            "end_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class CandidateProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    first_name = serializers.CharField(source="user.first_name", required=False, allow_blank=True)
    last_name = serializers.CharField(source="user.last_name", required=False, allow_blank=True)
    email = serializers.EmailField(source="user.email", required=False, allow_blank=True)
    phone_number = serializers.CharField(source="user.phone_number", required=False, allow_blank=True)
    username = serializers.CharField(source="user.username", read_only=True)
    video_count = serializers.SerializerMethodField()

    class Meta:
        model = CandidateProfile
        fields = (
            "id",
            "user",
            "username",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "sex",
            "social_channel_url",
            "follower_count",
            "profile_image_url",
            "is_profile_complete",
            "video_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "is_profile_complete", "created_at", "updated_at")

    def get_video_count(self, obj) -> int:
        return obj.videos.filter(is_active=True).count()

    def _get_platform(self, instance: CandidateProfile) -> str:
        competition = (
            instance.organization.competitions.order_by("-created_at").first()
        )
        return competition.social_platform if competition else "tiktok"

    def validate_social_channel_url(self, value):
        if not value:
            return value
        instance = getattr(self, "instance", None)
        platform = self._get_platform(instance) if instance else "tiktok"
        if self.context.get("social_platform"):
            platform = self.context["social_platform"]
        return validate_social_channel_url(value, platform)

    def validate(self, attrs):
        user_data = attrs.pop("user", {})
        if user_data:
            attrs["_user_data"] = user_data
        return attrs

    def update(self, instance, validated_data):
        user_data = validated_data.pop("_user_data", {})
        user = instance.user

        for field in ("first_name", "last_name", "email", "phone_number"):
            if field in user_data:
                setattr(user, field, user_data[field])
        user.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.is_profile_complete = bool(
            user.first_name
            and user.last_name
            and user.phone_number
            and instance.sex
            and instance.social_channel_url
            and instance.profile_image_url
        )
        instance.save()
        return instance


class CompetitionVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompetitionVideo
        fields = (
            "id",
            "url",
            "platform_video_id",
            "views",
            "likes",
            "comments",
            "shares",
            "engagement_score",
            "last_synced_at",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "platform_video_id",
            "views",
            "likes",
            "comments",
            "shares",
            "engagement_score",
            "last_synced_at",
            "created_at",
            "updated_at",
        )

    def validate_url(self, value):
        competition = self.context["competition"]
        normalized = validate_competition_video_url(value, competition.social_platform)
        if CompetitionVideo.objects.filter(
            competition=competition,
            url=normalized,
        ).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("This video is already registered.")
        return normalized

    def create(self, validated_data):
        competition = self.context["competition"]
        profile = self.context["candidate_profile"]
        url = validated_data["url"]
        video_id = extract_video_id(url, competition.social_platform)
        video = CompetitionVideo.objects.create(
            competition=competition,
            candidate_profile=profile,
            url=url,
            platform_video_id=video_id,
        )
        from competitions.sync import sync_video_metrics

        sync_video_metrics(video)
        video.refresh_from_db()
        return video


class CandidateCompetitionVideoSerializer(serializers.ModelSerializer):
    """Candidate-facing video payload — excludes engagement score."""

    class Meta:
        model = CompetitionVideo
        fields = (
            "id",
            "url",
            "platform_video_id",
            "views",
            "likes",
            "comments",
            "shares",
            "last_synced_at",
            "is_active",
        )
        read_only_fields = fields


class LeaderboardEntrySerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    candidate_id = serializers.IntegerField()
    name = serializers.CharField()
    username = serializers.CharField()
    initials = serializers.CharField()
    profile_image_url = serializers.CharField(allow_blank=True)
    views = serializers.IntegerField()
    likes = serializers.IntegerField()
    comments = serializers.IntegerField()
    shares = serializers.IntegerField()
    engagement_score = serializers.FloatField()
    video_count = serializers.IntegerField()
    last_synced_at = serializers.DateTimeField(allow_null=True)


class PublicCompetitionSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name")
    organization_slug = serializers.CharField(source="organization.slug")

    class Meta:
        model = Competition
        fields = (
            "id",
            "organization_name",
            "organization_slug",
            "title",
            "description",
            "social_platform",
            "registration_criteria",
            "scoring_criteria",
            "final_award",
            "status",
            "live_tracking_enabled",
            "tracking_interval_minutes",
            "start_at",
            "end_at",
        )


class CreateCandidateSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    phone_number = serializers.CharField(max_length=20)
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_phone_number(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Phone number is required.")
        if (
            User.objects.filter(phone_number=cleaned)
            .exclude(phone_number="")
            .exists()
        ):
            raise serializers.ValidationError(
                "A candidate with this phone number already exists."
            )
        return cleaned

    def create(self, validated_data):
        organization = self.context["organization"]
        password = validated_data.pop("password")

        user = User.objects.create(
            username=validated_data["username"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            email=validated_data.get("email", ""),
            phone_number=validated_data.get("phone_number", ""),
            role=User.Role.CANDIDATE,
            must_change_password=True,
        )
        user.set_password(password)
        user.save()

        OrganizationMember.objects.create(
            organization=organization,
            user=user,
            role=OrganizationMember.Role.CANDIDATE,
        )

        CandidateProfile.objects.create(
            user=user,
            organization=organization,
        )

        return user
