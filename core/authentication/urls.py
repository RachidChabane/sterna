from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    LogoutView,
    OAuthStateView,
    RefreshTokenView,
    EmailVerificationView,
    ResendVerificationView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    ChangePasswordView,
    UserProfileView,
    SessionListView,
    SocialAccountListView,
    SocialAccountDisconnectView,
    AvatarUploadView,
    serve_user_avatar,
    ConsentView,
    ConsentAttachView,
    DataExportRequestView,
    DataExportStatusView,
    AccountDeletionRequestView,
    AccountDeletionCancelView,
)
from .oauth_views import google_auth, google_one_tap_auth, github_auth

app_name = "authentication"

urlpatterns = [
    # Registration and Authentication
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", RefreshTokenView.as_view(), name="token-refresh"),
    # Email Verification
    path("verify-email/", EmailVerificationView.as_view(), name="verify-email"),
    path(
        "resend-verification/",
        ResendVerificationView.as_view(),
        name="resend-verification",
    ),
    # Password Reset
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    # Profile Management
    path("profile/", UserProfileView.as_view(), name="profile"),
    path("profile/avatar/", AvatarUploadView.as_view(), name="avatar-upload"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    # Avatar serving (public endpoint for image display)
    path("avatar/<str:user_id>/", serve_user_avatar, name="serve-avatar"),
    # Session Management
    path("sessions/", SessionListView.as_view(), name="sessions"),
    path(
        "sessions/<uuid:session_id>/", SessionListView.as_view(), name="session-detail"
    ),
    # Social Account Management
    path("social-accounts/", SocialAccountListView.as_view(), name="social-accounts"),
    path(
        "social-accounts/<uuid:account_id>/",
        SocialAccountDisconnectView.as_view(),
        name="social-account-disconnect",
    ),
    # OAuth Authentication
    path("google/", google_auth, name="google-auth"),
    path("google/one-tap/", google_one_tap_auth, name="google-one-tap"),
    path("github/", github_auth, name="github-auth"),
    path("oauth/state/", OAuthStateView.as_view(), name="oauth-state"),
    # Cookie Consent (ePrivacy + GDPR audit)
    path("consent/", ConsentView.as_view(), name="consent"),
    path("consent/attach/", ConsentAttachView.as_view(), name="consent-attach"),
    # GDPR Art. 15 — data export
    path("account/data-export/", DataExportRequestView.as_view(), name="data-export-request"),
    path(
        "account/data-export/<uuid:request_id>/",
        DataExportStatusView.as_view(),
        name="data-export-status",
    ),
    # GDPR Art. 17 — account deletion
    path(
        "account/delete-request/",
        AccountDeletionRequestView.as_view(),
        name="account-delete-request",
    ),
    path(
        "account/delete-request/cancel/",
        AccountDeletionCancelView.as_view(),
        name="account-delete-cancel",
    ),
]
