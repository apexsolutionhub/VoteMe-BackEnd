from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("voteMe", {"fields": ("role", "must_change_password")}),
    )
    list_display = (
        "username",
        "phone_number",
        "email",
        "role",
        "must_change_password",
        "is_active",
    )
    list_filter = ("role", "must_change_password", "is_active")
