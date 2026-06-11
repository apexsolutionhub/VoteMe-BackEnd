import re
import secrets

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers

from accounts.models import User
from accounts.serializers import UserSerializer
from competitions.models import Competition
from organizations.models import Organization, OrganizationMember


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "slug",
            "org_code",
            "logo_url",
            "plan",
            "status",
            "created_at",
        )
        read_only_fields = fields


class SignupSerializer(serializers.Serializer):
    organization_name = serializers.CharField(max_length=200)
    slug = serializers.SlugField(max_length=80, required=False, allow_blank=True)
    logo_url = serializers.URLField(max_length=500, required=False, allow_blank=True, default="")
    secret_code = serializers.CharField(max_length=128, write_only=True)
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)

    def validate_secret_code(self, value):
        expected = settings.SIGNUP_SECRET_CODE
        if not expected:
            raise serializers.ValidationError(
                "Registration is not configured. Contact voteMe support."
            )
        if not secrets.compare_digest(value, expected):
            raise serializers.ValidationError("Invalid secret code.")
        return value

    def validate_slug(self, value):
        if not value:
            return value
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", value):
            raise serializers.ValidationError(
                "Slug may only contain lowercase letters, numbers, and hyphens."
            )
        if Organization.objects.filter(slug=value).exists():
            raise serializers.ValidationError("This organization URL is already taken.")
        return value

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    @transaction.atomic
    def create(self, validated_data):
        org_name = validated_data["organization_name"]
        slug = validated_data.get("slug") or slugify(org_name) or "organization"

        base_slug = slug
        index = 1
        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{index}"
            index += 1

        organization = Organization.objects.create(
            name=org_name,
            slug=slug,
            logo_url=validated_data.get("logo_url", ""),
        )

        user = User.objects.create(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            role=User.Role.ADMIN,
            must_change_password=False,
        )
        user.set_password(validated_data["password"])
        user.save()

        membership = OrganizationMember.objects.create(
            organization=organization,
            user=user,
            role=OrganizationMember.Role.OWNER,
        )

        Competition.objects.create(
            organization=organization,
            title=f"{org_name} Engagement Competition",
            registration_criteria=(
                "Complete your profile with contact details, channel link, and competition videos."
            ),
            scoring_criteria=(
                "Rankings are based on weighted views, likes, comments, and shares."
            ),
            scoring_weights={"views": 1, "likes": 3, "comments": 5, "shares": 2},
        )

        return {
            "organization": organization,
            "user": user,
            "membership": membership,
        }


class SignupResponseSerializer(serializers.Serializer):
    organization = OrganizationSerializer()
    user = UserSerializer()
    access = serializers.CharField()
    refresh = serializers.CharField()
