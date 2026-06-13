from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from rest_framework import serializers

from accounts.models import User
from accounts.serializers import UserSerializer
from competitions.models import (
    CandidateProfile,
    Competition,
    CompetitionCriterion,
    CompetitionVideo,
)
from competitions.comment_mentions import normalize_comment_match_terms
from competitions.validators import (
    extract_video_id,
    validate_competition_video_url,
    validate_social_channel_url,
)
from organizations.models import OrganizationMember


class CompetitionSerializer(serializers.ModelSerializer):
    comment_scoring_approximate = serializers.SerializerMethodField()

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
            "comment_scoring_mode",
            "comment_match_terms",
            "comment_scoring_approximate",
            "start_at",
            "end_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "comment_scoring_approximate")

    def get_comment_scoring_approximate(self, obj: Competition) -> bool:
        if not obj.uses_matched_comment_scoring():
            return False
        from competitions.models import VideoComment

        return not VideoComment.objects.filter(
            video__competition=obj,
            video__is_active=True,
        ).exists()

    def validate_comment_match_terms(self, value):
        return normalize_comment_match_terms(value)

    def validate(self, attrs):
        mode = attrs.get(
            "comment_scoring_mode",
            getattr(self.instance, "comment_scoring_mode", Competition.CommentScoringMode.ALL),
        )
        terms = attrs.get(
            "comment_match_terms",
            getattr(self.instance, "comment_match_terms", []),
        )
        if isinstance(terms, str):
            terms = normalize_comment_match_terms(terms)
            attrs["comment_match_terms"] = terms

        if mode == Competition.CommentScoringMode.MATCHED and not terms:
            attrs["comment_scoring_mode"] = Competition.CommentScoringMode.ALL
            attrs["comment_match_terms"] = []
        return attrs


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
        annotated = getattr(obj, "video_count", None)
        if annotated is not None:
            return int(annotated)
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
            "title",
            "views",
            "likes",
            "comments",
            "shares",
            "engagement_score",
            "last_synced_at",
            "platform_published_at",
            "is_competition_eligible",
            "ineligibility_reason",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "platform_video_id",
            "title",
            "views",
            "likes",
            "comments",
            "shares",
            "engagement_score",
            "last_synced_at",
            "platform_published_at",
            "is_competition_eligible",
            "ineligibility_reason",
            "created_at",
            "updated_at",
        )

    def validate_url(self, value):
        competition = self.context["competition"]
        profile = self.context["candidate_profile"]
        platform = competition.social_platform
        normalized = validate_competition_video_url(value, platform)
        video_id = extract_video_id(normalized, platform)

        active_duplicates = CompetitionVideo.objects.filter(
            competition=competition,
            is_active=True,
        ).exclude(pk=getattr(self.instance, "pk", None))
        if active_duplicates.filter(url=normalized).exists() or (
            video_id and active_duplicates.filter(platform_video_id=video_id).exists()
        ):
            raise serializers.ValidationError("This video is already registered.")

        inactive_match = Q(url=normalized)
        if video_id:
            inactive_match |= Q(platform_video_id=video_id)
        owned_by_other = (
            CompetitionVideo.objects.filter(competition=competition)
            .filter(inactive_match)
            .exclude(candidate_profile=profile)
            .exists()
        )
        if owned_by_other:
            raise serializers.ValidationError("This video is already registered.")

        return normalized

    def _reactivate_video(
        self,
        video: CompetitionVideo,
        *,
        url: str,
        platform_video_id: str,
    ) -> CompetitionVideo:
        video.is_active = True
        video.url = url
        video.platform_video_id = platform_video_id or video.platform_video_id
        video.title = ""
        video.views = 0
        video.likes = 0
        video.comments = 0
        video.scored_comments = 0
        video.shares = 0
        video.brand_mention_comments = 0
        video.engagement_score = 0
        video.last_synced_at = None
        video.platform_published_at = None
        video.save()
        evaluate_video_eligibility(video, persist=True)
        return video

    def create(self, validated_data):
        competition = self.context["competition"]
        profile = self.context["candidate_profile"]
        url = validated_data["url"]
        video_id = extract_video_id(url, competition.social_platform)

        inactive_match = Q(url=url)
        if video_id:
            inactive_match |= Q(platform_video_id=video_id)

        existing = (
            CompetitionVideo.objects.filter(
                competition=competition,
                candidate_profile=profile,
                is_active=False,
            )
            .filter(inactive_match)
            .first()
        )
        if existing:
            return self._reactivate_video(
                existing,
                url=url,
                platform_video_id=video_id,
            )

        video = CompetitionVideo.objects.create(
            competition=competition,
            candidate_profile=profile,
            url=url,
            platform_video_id=video_id,
        )
        evaluate_video_eligibility(video, persist=True)
        return video


class CandidateCompetitionVideoSerializer(serializers.ModelSerializer):
    """Candidate-facing video payload — excludes engagement score."""

    sync_status = serializers.SerializerMethodField()

    class Meta:
        model = CompetitionVideo
        fields = (
            "id",
            "url",
            "platform_video_id",
            "title",
            "views",
            "likes",
            "comments",
            "shares",
            "last_synced_at",
            "platform_published_at",
            "is_competition_eligible",
            "ineligibility_reason",
            "sync_status",
            "is_active",
        )
        read_only_fields = fields

    def get_sync_status(self, obj: CompetitionVideo) -> str:
        if obj.last_synced_at:
            return "synced"
        return "pending"


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


class CompetitionCriterionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompetitionCriterion
        fields = (
            "id",
            "kind",
            "metric_key",
            "evaluation_mode",
            "title",
            "description",
            "target_value",
            "weight_value",
            "weight_input_type",
            "weight_display",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        kind = attrs.get("kind") or getattr(self.instance, "kind", None)
        evaluation_mode = attrs.get("evaluation_mode") or getattr(
            self.instance, "evaluation_mode", CompetitionCriterion.EvaluationMode.ABSOLUTE
        )
        weight_input_type = attrs.get("weight_input_type") or getattr(
            self.instance,
            "weight_input_type",
            CompetitionCriterion.WeightInputType.NUMBER,
        )
        weight_display = attrs.get("weight_display")
        weight_value = attrs.get("weight_value")

        if kind == CompetitionCriterion.Kind.METRIC:
            if weight_input_type == CompetitionCriterion.WeightInputType.PERCENTAGE:
                raw = weight_display if weight_display is not None else weight_value
                if raw is None:
                    raise serializers.ValidationError(
                        {"weight_display": "Enter a percentage such as 30%."}
                    )
                token = str(raw).strip().replace("%", "")
                try:
                    attrs["weight_value"] = float(token)
                except (TypeError, ValueError) as exc:
                    raise serializers.ValidationError(
                        {"weight_display": "Enter a valid percentage."}
                    ) from exc
                attrs["weight_display"] = f"{attrs['weight_value']:.0f}%"
            elif weight_input_type == CompetitionCriterion.WeightInputType.WORD:
                if not (weight_display or "").strip():
                    raise serializers.ValidationError(
                        {"weight_display": "Enter a weight word such as high or medium."}
                    )
            elif weight_value is None:
                raise serializers.ValidationError(
                    {"weight_value": "Enter a numeric weight."}
                )

        if kind == CompetitionCriterion.Kind.MILESTONE:
            if evaluation_mode == CompetitionCriterion.EvaluationMode.ABSOLUTE:
                metric_key = attrs.get("metric_key") or getattr(
                    self.instance, "metric_key", None
                )
                if (
                    metric_key != CompetitionCriterion.MetricKey.PROFILE_COMPLETE
                    and attrs.get("target_value") is None
                    and getattr(self.instance, "target_value", None) is None
                ):
                    raise serializers.ValidationError(
                        {"target_value": "Absolute milestones need a target value."}
                    )
        return attrs


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
