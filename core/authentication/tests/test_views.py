from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone
from datetime import timedelta

from authentication.models import (
    User,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
)
from authentication.jwt_utils import JWTManager


class AuthenticationViewsTest(TestCase):
    """Test cases for authentication views."""

    def setUp(self):
        # Reset the signup-guard / OAuth state buckets so test ordering
        # in the same process doesn't poison the IP velocity counter
        # (LocMemCache is shared across tests in pytest).
        cache.clear()
        self.client = APIClient()
        self.register_url = reverse("authentication:register")
        self.login_url = reverse("authentication:login")
        self.logout_url = reverse("authentication:logout")
        self.refresh_url = reverse("authentication:token-refresh")
        self.profile_url = reverse("authentication:profile")

    def test_user_registration(self):
        """Test user registration."""
        data = {
            "email": "newuser@example.com",
            "password": "NewPassword123!",
            "password_confirm": "NewPassword123!",
            "full_name": "New User",
        }

        response = self.client.post(self.register_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("message", response.data)
        self.assertIn("user", response.data)

        # Check user was created
        user = User.objects.get(email="newuser@example.com")
        self.assertEqual(user.full_name, "New User")
        self.assertFalse(user.is_verified)

        # Check verification token was created
        token_exists = EmailVerificationToken.objects.filter(user=user).exists()
        self.assertTrue(token_exists)

    def test_registration_with_existing_email(self):
        """Test registration with already registered email."""
        User.objects.create_user(email="existing@example.com", password="Password123!")

        data = {
            "email": "existing@example.com",
            "password": "NewPassword123!",
            "password_confirm": "NewPassword123!",
        }

        response = self.client.post(self.register_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_registration_password_mismatch(self):
        """Test registration with mismatched passwords."""
        data = {
            "email": "newuser@example.com",
            "password": "Password123!",
            "password_confirm": "DifferentPassword123!",
        }

        response = self.client.post(self.register_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    def test_user_login(self):
        """Test user login."""
        User.objects.create_user(
            email="testuser@example.com", password="TestPassword123!"
        )

        data = {"email": "testuser@example.com", "password": "TestPassword123!"}

        response = self.client.post(self.login_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.data)
        self.assertIn("refresh_token", response.data)
        self.assertIn("token_type", response.data)
        self.assertEqual(response.data["token_type"], "Bearer")
        self.assertIn("user", response.data)

    def test_login_with_invalid_credentials(self):
        """Test login with invalid credentials."""
        User.objects.create_user(
            email="testuser@example.com", password="TestPassword123!"
        )

        data = {"email": "testuser@example.com", "password": "WrongPassword!"}

        response = self.client.post(self.login_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_with_inactive_user(self):
        """Test login with inactive user."""
        user = User.objects.create_user(
            email="inactive@example.com", password="TestPassword123!"
        )
        user.is_active = False
        user.save()

        data = {"email": "inactive@example.com", "password": "TestPassword123!"}

        response = self.client.post(self.login_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout(self):
        """Test user logout."""
        User.objects.create_user(
            email="testuser@example.com", password="TestPassword123!"
        )

        # Login to get tokens
        login_data = {"email": "testuser@example.com", "password": "TestPassword123!"}
        login_response = self.client.post(self.login_url, login_data, format="json")
        access_token = login_response.data["access_token"]
        refresh_token = login_response.data["refresh_token"]

        # Logout with refresh token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        logout_data = {"refresh_token": refresh_token}
        response = self.client.post(self.logout_url, logout_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

        # Check token is revoked (DB stores the SHA-256 hash)
        db_token = RefreshToken.objects.get(
            token=RefreshToken.hash_token(refresh_token)
        )
        self.assertTrue(db_token.is_revoked)

    def test_refresh_token(self):
        """Test refreshing access token."""
        user = User.objects.create_user(
            email="testuser@example.com", password="TestPassword123!"
        )

        # Create token pair
        tokens = JWTManager.create_token_pair(user)
        refresh_token = tokens["refresh_token"]

        # Refresh the token
        data = {"refresh_token": refresh_token}
        response = self.client.post(self.refresh_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.data)
        self.assertIn("token_type", response.data)
        self.assertIn("expires_in", response.data)
        # Rotation: the endpoint returns a fresh refresh token
        self.assertIn("refresh_token", response.data)
        self.assertNotEqual(response.data["refresh_token"], refresh_token)

    def test_get_user_profile(self):
        """Test getting user profile."""
        user = User.objects.create_user(
            email="testuser@example.com",
            password="TestPassword123!",
            full_name="Test User",
        )

        # Get access token
        tokens = JWTManager.create_token_pair(user)
        access_token = tokens["access_token"]

        # Get profile
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "testuser@example.com")
        self.assertEqual(response.data["full_name"], "Test User")

    def test_update_user_profile(self):
        """Test updating user profile."""
        user = User.objects.create_user(
            email="testuser@example.com",
            password="TestPassword123!",
            full_name="Test User",
        )

        # Get access token
        tokens = JWTManager.create_token_pair(user)
        access_token = tokens["access_token"]

        # Update profile
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        data = {"full_name": "Updated Name"}
        response = self.client.patch(self.profile_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["full_name"], "Updated Name")

        # Check database
        user.refresh_from_db()
        self.assertEqual(user.full_name, "Updated Name")

    def test_unauthenticated_profile_access(self):
        """Test accessing profile without authentication."""
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class EmailVerificationViewsTest(TestCase):
    """Test cases for email verification views."""

    def setUp(self):
        self.client = APIClient()
        self.verify_url = reverse("authentication:verify-email")
        self.resend_url = reverse("authentication:resend-verification")

        self.user = User.objects.create_user(
            email="testuser@example.com", password="TestPassword123!"
        )

    def test_email_verification(self):
        """Test email verification."""
        token = EmailVerificationToken.objects.create(
            user=self.user,
            token="verification_token",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        data = {"token": "verification_token"}
        response = self.client.post(self.verify_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

        # Check user is verified
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified)

        # Check token is marked as used
        token.refresh_from_db()
        self.assertTrue(token.is_used)

    def test_verification_with_expired_token(self):
        """Test verification with expired token."""
        EmailVerificationToken.objects.create(
            user=self.user,
            token="expired_token",
            expires_at=timezone.now() - timedelta(hours=1),
        )

        data = {"token": "expired_token"}
        response = self.client.post(self.verify_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resend_verification(self):
        """Test resending verification email."""
        data = {"email": "testuser@example.com"}
        response = self.client.post(self.resend_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

        # Check new token was created
        tokens = EmailVerificationToken.objects.filter(user=self.user, is_used=False)
        self.assertEqual(tokens.count(), 1)

    def test_resend_for_verified_user(self):
        """Test resending verification for already verified user."""
        self.user.is_verified = True
        self.user.save()

        data = {"email": "testuser@example.com"}
        response = self.client.post(self.resend_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PasswordResetViewsTest(TestCase):
    """Test cases for password reset views."""

    def setUp(self):
        self.client = APIClient()
        self.reset_request_url = reverse("authentication:password-reset")
        self.reset_confirm_url = reverse("authentication:password-reset-confirm")

        self.user = User.objects.create_user(
            email="testuser@example.com", password="OldPassword123!"
        )

    def test_password_reset_request(self):
        """Test requesting password reset."""
        data = {"email": "testuser@example.com"}
        response = self.client.post(self.reset_request_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

        # Check token was created
        token_exists = PasswordResetToken.objects.filter(user=self.user).exists()
        self.assertTrue(token_exists)

    def test_password_reset_request_nonexistent_email(self):
        """Test requesting reset for non-existent email."""
        data = {"email": "nonexistent@example.com"}
        response = self.client.post(self.reset_request_url, data, format="json")

        # Should still return success to avoid email enumeration
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

    def test_password_reset_confirm(self):
        """Test confirming password reset."""
        token = PasswordResetToken.objects.create(
            user=self.user,
            token="reset_token",
            expires_at=timezone.now() + timedelta(hours=1),
        )

        data = {
            "token": "reset_token",
            "password": "NewPassword123!",
            "password_confirm": "NewPassword123!",
        }
        response = self.client.post(self.reset_confirm_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

        # Check password was changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassword123!"))

        # Check token is marked as used
        token.refresh_from_db()
        self.assertTrue(token.is_used)
