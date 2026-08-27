"""
Attaches drf-spectacular request/response schemas to the auth views.

These views build their responses as plain dicts (see views.py /
oauth_views.py) rather than through a `serializer_class` drf-spectacular
can auto-discover, so every operation needs an explicit annotation.
Applying them here — rather than as decorators in views.py /
oauth_views.py — keeps those view modules' line counts untouched:
`extend_schema` / `extend_schema_view` mutate the view class or
function in place, so no reassignment is needed for it to take effect.
This mirrors conversations.serializers.register_spark_serializer,
which keeps a different view's schema wiring out of the file that
defines the view, for the same reason.

Called once from AuthenticationConfig.ready(). Documentation only: no
serializer here is used to validate a request or build a response, so
the wire format is unchanged.
"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view

from . import views
from .schema_serializers import (
    AccountDeletionCancelResponseSerializer,
    AccountDeletionCreateResponseSerializer,
    AccountDeletionRequestSerializer,
    AvatarUploadRequestSerializer,
    AvatarUploadResponseSerializer,
    CancelDeletionRequestSerializer,
    ChangePasswordRequestSerializer,
    ConsentAttachResponseSerializer,
    ConsentResponseSerializer,
    DataExportCreateResponseSerializer,
    DataExportStatusResponseSerializer,
    EmailVerificationResponseSerializer,
    LoginResponseSerializer,
    LogoutRequestSerializer,
    MessageResponseSerializer,
    OAuthStateResponseSerializer,
    RegisterResponseSerializer,
    SessionListResponseSerializer,
    TokenPairSerializer,
)
from .serializers import (
    ConsentAttachSerializer,
    ConsentSerializer,
    EmailVerificationSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RefreshTokenSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    SocialAccountSerializer,
    UserSerializer,
)

# Non-2xx bodies vary per failure branch (a validation-error map here, a
# `{"error": "..."}` there); OBJECT documents "this returns a JSON
# object" honestly without overclaiming a shape none of the branches
# share.
ERROR = OpenApiTypes.OBJECT


def apply_auth_schema() -> None:
    """Attach request/response schemas to every auth view."""

    extend_schema_view(
        post=extend_schema(
            request=RegisterSerializer,
            responses={
                201: OpenApiResponse(RegisterResponseSerializer, description="Account created; verification email sent."),
                400: ERROR,
                403: ERROR,
            },
        ),
    )(views.RegisterView)

    extend_schema_view(
        post=extend_schema(
            responses={200: OAuthStateResponseSerializer},
        ),
    )(views.OAuthStateView)

    extend_schema_view(
        post=extend_schema(
            request=LoginSerializer,
            responses={
                200: OpenApiResponse(LoginResponseSerializer, description="Login successful."),
                400: ERROR,
            },
        ),
    )(views.LoginView)

    extend_schema_view(
        post=extend_schema(
            request=LogoutRequestSerializer,
            responses={200: MessageResponseSerializer},
        ),
    )(views.LogoutView)

    extend_schema_view(
        post=extend_schema(
            request=RefreshTokenSerializer,
            responses={200: TokenPairSerializer, 401: ERROR, 400: ERROR},
        ),
    )(views.RefreshTokenView)

    extend_schema_view(
        post=extend_schema(
            request=EmailVerificationSerializer,
            responses={200: EmailVerificationResponseSerializer, 400: ERROR},
        ),
    )(views.EmailVerificationView)

    extend_schema_view(
        post=extend_schema(
            request=ResendVerificationSerializer,
            responses={200: MessageResponseSerializer, 400: ERROR},
        ),
    )(views.ResendVerificationView)

    extend_schema_view(
        post=extend_schema(
            request=PasswordResetRequestSerializer,
            responses={200: MessageResponseSerializer},
        ),
    )(views.PasswordResetRequestView)

    extend_schema_view(
        post=extend_schema(
            request=PasswordResetConfirmSerializer,
            responses={200: MessageResponseSerializer, 400: ERROR},
        ),
    )(views.PasswordResetConfirmView)

    extend_schema_view(
        post=extend_schema(
            request=ChangePasswordRequestSerializer,
            responses={200: MessageResponseSerializer, 400: ERROR},
        ),
    )(views.ChangePasswordView)

    extend_schema_view(
        get=extend_schema(responses={200: UserSerializer}),
        patch=extend_schema(
            request=UserSerializer, responses={200: UserSerializer, 400: ERROR}
        ),
    )(views.UserProfileView)

    extend_schema_view(
        get=extend_schema(responses={200: SessionListResponseSerializer}),
        delete=extend_schema(responses={200: MessageResponseSerializer, 404: ERROR}),
    )(views.SessionListView)

    extend_schema_view(
        get=extend_schema(responses={200: SocialAccountSerializer(many=True)}),
    )(views.SocialAccountListView)

    extend_schema_view(
        delete=extend_schema(
            responses={200: MessageResponseSerializer, 400: ERROR, 404: ERROR}
        ),
    )(views.SocialAccountDisconnectView)

    extend_schema_view(
        post=extend_schema(
            request=AvatarUploadRequestSerializer,
            responses={200: AvatarUploadResponseSerializer, 400: ERROR, 500: ERROR},
        ),
        delete=extend_schema(responses={200: MessageResponseSerializer, 500: ERROR}),
    )(views.AvatarUploadView)

    extend_schema_view(
        get=extend_schema(responses={200: ConsentResponseSerializer}),
        post=extend_schema(
            request=ConsentSerializer,
            responses={200: ConsentResponseSerializer, 400: ERROR},
        ),
    )(views.ConsentView)

    extend_schema_view(
        post=extend_schema(
            request=ConsentAttachSerializer,
            responses={200: ConsentAttachResponseSerializer, 400: ERROR},
        ),
    )(views.ConsentAttachView)

    extend_schema_view(
        post=extend_schema(
            responses={202: DataExportCreateResponseSerializer, 429: ERROR}
        ),
    )(views.DataExportRequestView)

    extend_schema_view(
        get=extend_schema(
            responses={200: DataExportStatusResponseSerializer, 404: ERROR}
        ),
    )(views.DataExportStatusView)

    extend_schema_view(
        post=extend_schema(
            request=AccountDeletionRequestSerializer,
            responses={202: AccountDeletionCreateResponseSerializer, 400: ERROR},
        ),
    )(views.AccountDeletionRequestView)

    extend_schema_view(
        post=extend_schema(
            request=CancelDeletionRequestSerializer,
            responses={200: AccountDeletionCancelResponseSerializer, 400: ERROR},
        ),
    )(views.AccountDeletionCancelView)

    extend_schema(
        responses={200: OpenApiTypes.BINARY, 404: ERROR, 503: ERROR, 500: ERROR},
    )(views.serve_user_avatar)
