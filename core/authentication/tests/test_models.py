from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from authentication.models import (
    User,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
)


class UserModelTest(TestCase):
    """Test cases for User model."""

    def setUp(self):
        self.email = "test@example.com"
        self.password = "TestPassword123!"

    def test_create_user(self):
        """Test creating a regular user."""
        user = User.objects.create_user(
            email=self.email, password=self.password, full_name="Test User"
        )

        self.assertEqual(user.email, self.email)
        self.assertTrue(user.check_password(self.password))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_verified)

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(email=self.email, password=self.password)

        self.assertEqual(user.email, self.email)
        self.assertTrue(user.check_password(self.password))
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_create_user_without_email(self):
        """Test that creating a user without email raises error."""
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password=self.password)

    def test_email_normalization(self):
        """Test that email is normalized."""
        user = User.objects.create_user(
            email="Test@EXAMPLE.COM", password=self.password
        )
        self.assertEqual(user.email, "Test@example.com")

    def test_get_full_name(self):
        """Test get_full_name method."""
        user = User.objects.create_user(
            email=self.email, password=self.password, full_name="John Doe"
        )
        self.assertEqual(user.get_full_name(), "John Doe")

        user_no_name = User.objects.create_user(
            email="another@example.com", password=self.password
        )
        self.assertEqual(user_no_name.get_full_name(), "another@example.com")

    def test_get_short_name(self):
        """Test get_short_name method."""
        user = User.objects.create_user(
            email=self.email, password=self.password, full_name="John Doe"
        )
        self.assertEqual(user.get_short_name(), "John")

        user_no_name = User.objects.create_user(
            email="another@example.com", password=self.password
        )
        self.assertEqual(user_no_name.get_short_name(), "another")


class EmailVerificationTokenTest(TestCase):
    """Test cases for EmailVerificationToken model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPassword123!"
        )

    def test_create_token(self):
        """Test creating an email verification token."""
        token = EmailVerificationToken.objects.create(
            user=self.user,
            token="test_token",
            expires_at=timezone.now() + timedelta(hours=24),
        )

        self.assertEqual(token.user, self.user)
        self.assertEqual(token.token, "test_token")
        self.assertFalse(token.is_used)
        self.assertTrue(token.is_valid())

    def test_expired_token(self):
        """Test that expired token is invalid."""
        token = EmailVerificationToken.objects.create(
            user=self.user,
            token="test_token",
            expires_at=timezone.now() - timedelta(hours=1),
        )

        self.assertFalse(token.is_valid())

    def test_used_token(self):
        """Test that used token is invalid."""
        token = EmailVerificationToken.objects.create(
            user=self.user,
            token="test_token",
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=True,
        )

        self.assertFalse(token.is_valid())


class PasswordResetTokenTest(TestCase):
    """Test cases for PasswordResetToken model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPassword123!"
        )

    def test_create_token(self):
        """Test creating a password reset token."""
        token = PasswordResetToken.objects.create(
            user=self.user,
            token="reset_token",
            expires_at=timezone.now() + timedelta(hours=1),
        )

        self.assertEqual(token.user, self.user)
        self.assertEqual(token.token, "reset_token")
        self.assertFalse(token.is_used)
        self.assertTrue(token.is_valid())

    def test_expired_token(self):
        """Test that expired token is invalid."""
        token = PasswordResetToken.objects.create(
            user=self.user,
            token="reset_token",
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        self.assertFalse(token.is_valid())


class RefreshTokenTest(TestCase):
    """Test cases for RefreshToken model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPassword123!"
        )

    def test_create_refresh_token(self):
        """Test creating a refresh token."""
        token = RefreshToken.objects.create(
            user=self.user,
            token="refresh_token_value",
            expires_at=timezone.now() + timedelta(days=7),
            user_agent="Mozilla/5.0",
            ip_address="127.0.0.1",
        )

        self.assertEqual(token.user, self.user)
        self.assertEqual(token.token, "refresh_token_value")
        self.assertFalse(token.is_revoked)
        self.assertTrue(token.is_valid())
        self.assertEqual(token.user_agent, "Mozilla/5.0")
        self.assertEqual(token.ip_address, "127.0.0.1")

    def test_revoked_token(self):
        """Test that revoked token is invalid."""
        token = RefreshToken.objects.create(
            user=self.user,
            token="refresh_token_value",
            expires_at=timezone.now() + timedelta(days=7),
            is_revoked=True,
        )

        self.assertFalse(token.is_valid())

    def test_expired_refresh_token(self):
        """Test that expired refresh token is invalid."""
        token = RefreshToken.objects.create(
            user=self.user,
            token="refresh_token_value",
            expires_at=timezone.now() - timedelta(days=1),
        )

        self.assertFalse(token.is_valid())
