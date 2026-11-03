from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm

from accounts.models import User


class UserCreateForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreateForm
    ordering = ("-date_joined",)
    list_display = ("email", "display_name", "role", "is_staff", "is_active", "date_joined")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "display_name")
    readonly_fields = ("id", "google_sub", "date_joined", "last_login")
    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        ("Profile", {"fields": ("display_name", "birth_date", "role", "google_sub")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
