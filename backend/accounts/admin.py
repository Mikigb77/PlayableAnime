from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm

from accounts import tokens
from accounts.models import AuthSession, User


class UserCreateForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email",)


class AuthSessionInline(admin.TabularInline):
    model = AuthSession
    extra = 0
    fields = ("method", "created_at", "last_used_at", "revoked_at", "revoked_reason")
    readonly_fields = fields
    can_delete = False
    ordering = ("-last_used_at",)
    show_change_link = True

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreateForm
    ordering = ("-date_joined",)
    list_display = ("email", "display_name", "role", "is_staff", "is_active", "date_joined")
    list_filter = ("role", "email_verified", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "display_name")
    # The owner role comes only from OWNER_EMAILS through a verified Google sign-in (K7).
    readonly_fields = ("id", "role", "google_sub", "email_verified", "date_joined", "last_login")
    fieldsets = (
        (None, {"fields": ("id", "email", "email_verified", "password")}),
        (
            "Profile",
            {"fields": ("display_name", "birth_date", "role", "google_sub", "content_prefs")},
        ),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
    inlines = [AuthSessionInline]


@admin.register(AuthSession)
class AuthSessionAdmin(admin.ModelAdmin):
    """Signed-in devices. Revoking one signs it out within a request (T8)."""

    list_display = ("user", "method", "created_at", "last_used_at", "revoked_at", "revoked_reason")
    list_filter = ("method", "revoked_reason")
    search_fields = ("user__email", "id")
    raw_id_fields = ("user",)
    readonly_fields = (
        "id",
        "user",
        "method",
        "created_at",
        "last_used_at",
        "revoked_at",
        "revoked_reason",
    )
    actions = ["revoke"]

    def has_add_permission(self, request) -> bool:
        return False

    @admin.action(description="Sign out the selected sessions")
    def revoke(self, request, queryset) -> None:
        count = tokens.revoke(queryset, "admin")
        self.message_user(request, f"Signed out {count} session(s).")
