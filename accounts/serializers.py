from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.models import User
from organizations.mixins import resolve_membership
from organizations.models import OrganizationMember


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "phone_number",
            "first_name",
            "last_name",
            "role",
            "must_change_password",
        )


class OrganizationContextSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    org_code = serializers.CharField()
    membership_role = serializers.CharField()


class AuthUserSerializer(UserSerializer):
    organization = OrganizationContextSerializer(required=False)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=User.Role.choices)
    organization_slug = serializers.SlugField(required=False, allow_blank=True)

    def validate_username(self, value):
        return value.strip()

    def validate(self, attrs):
        attrs["password"] = attrs["password"].strip()
        slug = attrs.get("organization_slug")
        if isinstance(slug, str):
            attrs["organization_slug"] = slug.strip()

        user = authenticate(
            username=attrs["username"],
            password=attrs["password"],
        )

        if user is None:
            raise serializers.ValidationError("Invalid username or password.")

        if not user.is_active:
            raise serializers.ValidationError("This account is disabled.")

        if user.role != attrs["role"]:
            raise serializers.ValidationError(
                "You do not have access to this portal."
            )

        organization_slug = attrs.get("organization_slug") or None
        try:
            organization, membership = resolve_membership(user, organization_slug)
        except Exception as exc:
            detail = getattr(exc, "detail", str(exc))
            if isinstance(detail, list):
                detail = " ".join(str(item) for item in detail)
            raise serializers.ValidationError(str(detail)) from exc

        expected_membership_roles = {
            User.Role.ADMIN: {
                OrganizationMember.Role.OWNER,
                OrganizationMember.Role.ADMIN,
            },
            User.Role.CANDIDATE: {OrganizationMember.Role.CANDIDATE},
        }

        if membership.role not in expected_membership_roles[user.role]:
            raise serializers.ValidationError(
                "You do not have access to this portal for this organization."
            )

        attrs["user"] = user
        attrs["organization"] = organization
        attrs["membership"] = membership
        return attrs


class ProfileUpdateSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = (
            "email",
            "phone_number",
            "first_name",
            "last_name",
        )

    def validate_phone_number(self, value):
        cleaned = value.strip()
        user = self.instance

        if user.is_candidate and not cleaned:
            raise serializers.ValidationError("Phone number is required.")

        if cleaned and len(cleaned) < 8:
            raise serializers.ValidationError("Enter a valid phone number.")

        if (
            cleaned
            and User.objects.filter(phone_number=cleaned)
            .exclude(pk=user.pk)
            .exclude(phone_number="")
            .exists()
        ):
            raise serializers.ValidationError(
                "This phone number is already in use."
            )

        return cleaned

    def validate_email(self, value):
        cleaned = value.strip()
        user = self.instance

        if cleaned and User.objects.filter(email=cleaned).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This email is already in use.")

        return cleaned


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        validate_password(attrs["new_password"], self.context["request"].user)
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.must_change_password = False
        user.save()
        user.refresh_from_db()
        return user


class LegacyCreateCandidateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    phone_number = serializers.CharField(max_length=20)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "password",
            "phone_number",
            "first_name",
            "last_name",
        )

    def validate_phone_number(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Phone number is required.")
        if len(cleaned) < 8:
            raise serializers.ValidationError("Enter a valid phone number.")
        if (
            User.objects.filter(phone_number=cleaned)
            .exclude(phone_number="")
            .exists()
        ):
            raise serializers.ValidationError(
                "A candidate with this phone number already exists."
            )
        return cleaned

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create(
            **validated_data,
            role=User.Role.CANDIDATE,
            must_change_password=True,
        )
        user.set_password(password)
        user.save()
        return user
