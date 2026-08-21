from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
import jwt

from authentication.models import User, RefreshToken
from authentication.jwt_utils import JWTManager


@override_settings(
    JWT_SECRET_KEY="test_secret_key",
    JWT_ALGORITHM="HS256",
    JWT_ACCESS_TOKEN_LIFETIME=timedelta(minutes=15),
    JWT_REFRESH_TOKEN_LIFETIME=timedelta(days=7),
)
class JWTManagerTest(TestCase):
    """Test cases for JWT Manager."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPassword123!"
        )

    def test_create_access_token(self):
        """Test creating an access token."""
        token = JWTManager.create_access_token(self.user)

        # Decode token
        payload = jwt.decode(token, "test_secret_key", algorithms=["HS256"])

        self.assertEqual(payload["user_id"], str(self.user.id))
        self.assertEqual(payload["email"], self.user.email)
        self.assertEqual(payload["type"], "access")
        self.assertIn("exp", payload)
        self.assertIn("iat", payload)
        self.assertIn("jti", payload)

    def test_create_refresh_token(self):
        """Test creating a refresh token."""
        token, expires_at = JWTManager.create_refresh_token(self.user)

        # Decode token
        payload = jwt.decode(token, "test_secret_key", algorithms=["HS256"])

        self.assertEqual(payload["user_id"], str(self.user.id))
        self.assertEqual(payload["email"], self.user.email)
        self.assertEqual(payload["type"], "refresh")
        self.assertIn("exp", payload)
        self.assertIn("iat", payload)
        self.assertIn("jti", payload)
        self.assertIsNotNone(expires_at)

    def test_verify_valid_access_token(self):
        """Test verifying a valid access token."""
        token = JWTManager.create_access_token(self.user)
        payload = JWTManager.verify_token(token, token_type="access")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["user_id"], str(self.user.id))
        self.assertEqual(payload["type"], "access")

    def test_verify_invalid_token_type(self):
        """Test verifying token with wrong type."""
        token = JWTManager.create_access_token(self.user)
        payload = JWTManager.verify_token(token, token_type="refresh")

        self.assertIsNone(payload)

    def test_verify_expired_token(self):
        """Test verifying an expired token."""
        # Create token with past expiry
        now = timezone.now()
        payload = {
            "user_id": str(self.user.id),
            "email": self.user.email,
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "jti": "test_jti",
        }

        token = jwt.encode(payload, "test_secret_key", algorithm="HS256")

        result = JWTManager.verify_token(token, token_type="access")
        self.assertIsNone(result)

    def test_verify_invalid_token(self):
        """Test verifying an invalid token."""
        result = JWTManager.verify_token("invalid_token", token_type="access")
        self.assertIsNone(result)

    def test_create_token_pair(self):
        """Test creating a token pair."""
        tokens = JWTManager.create_token_pair(self.user)

        self.assertIn("access_token", tokens)
        self.assertIn("refresh_token", tokens)
        self.assertEqual(tokens["token_type"], "Bearer")
        self.assertEqual(tokens["expires_in"], 900)  # 15 minutes

        # Check that the refresh token is stored hashed (never plaintext)
        db_token = RefreshToken.objects.get(
            token=RefreshToken.hash_token(tokens["refresh_token"])
        )
        self.assertEqual(db_token.user, self.user)
        self.assertFalse(db_token.is_revoked)
        self.assertFalse(
            RefreshToken.objects.filter(token=tokens["refresh_token"]).exists()
        )

    def test_refresh_access_token(self):
        """Test refreshing an access token (rotates the refresh token)."""
        # Create initial token pair
        tokens = JWTManager.create_token_pair(self.user)
        refresh_token = tokens["refresh_token"]

        # Refresh the access token
        new_tokens = JWTManager.refresh_access_token(refresh_token)

        self.assertIsNotNone(new_tokens)
        self.assertIn("access_token", new_tokens)
        self.assertIn("refresh_token", new_tokens)
        self.assertEqual(new_tokens["token_type"], "Bearer")
        self.assertEqual(new_tokens["expires_in"], 900)

        # Rotation: a NEW refresh token is issued, the old one revoked
        self.assertNotEqual(new_tokens["refresh_token"], refresh_token)
        old_db = RefreshToken.objects.get(
            token=RefreshToken.hash_token(refresh_token)
        )
        new_db = RefreshToken.objects.get(
            token=RefreshToken.hash_token(new_tokens["refresh_token"])
        )
        self.assertTrue(old_db.is_revoked)
        self.assertFalse(new_db.is_revoked)
        # Successor stays in the same rotation family
        self.assertEqual(old_db.family, new_db.family)

        # Verify the new access token is valid
        payload = JWTManager.verify_token(
            new_tokens["access_token"], token_type="access"
        )
        self.assertIsNotNone(payload)
        self.assertEqual(payload["user_id"], str(self.user.id))

    def test_refresh_with_invalid_token(self):
        """Test refreshing with an invalid refresh token."""
        result = JWTManager.refresh_access_token("invalid_token")
        self.assertIsNone(result)

    def test_refresh_with_revoked_token(self):
        """Test refreshing with a revoked refresh token."""
        # Create token pair
        tokens = JWTManager.create_token_pair(self.user)
        refresh_token = tokens["refresh_token"]

        # Revoke the token
        JWTManager.revoke_refresh_token(refresh_token)

        # Try to refresh
        result = JWTManager.refresh_access_token(refresh_token)
        self.assertIsNone(result)

    def test_refresh_reuse_revokes_family(self):
        """Reusing a rotated refresh token revokes the whole family."""
        tokens = JWTManager.create_token_pair(self.user)
        old_refresh = tokens["refresh_token"]

        # Legitimate rotation
        new_tokens = JWTManager.refresh_access_token(old_refresh)
        self.assertIsNotNone(new_tokens)
        new_refresh = new_tokens["refresh_token"]

        # Push the replay outside the concurrent-refresh grace window
        RefreshToken.objects.filter(
            token=RefreshToken.hash_token(old_refresh)
        ).update(
            last_used=timezone.now()
            - JWTManager.get_rotation_grace()
            - timedelta(seconds=1)
        )

        # Attacker replays the old (now revoked) token
        with self.assertLogs("authentication.jwt", level="WARNING") as logs:
            result = JWTManager.refresh_access_token(old_refresh)
        self.assertIsNone(result)
        self.assertTrue(
            any("refresh_token_reuse_detected" in line for line in logs.output)
        )

        # The successor is collateral damage: the whole family is dead
        new_db = RefreshToken.objects.get(
            token=RefreshToken.hash_token(new_refresh)
        )
        self.assertTrue(new_db.is_revoked)
        self.assertIsNone(JWTManager.refresh_access_token(new_refresh))

    def test_refresh_reuse_within_grace_window(self):
        """Concurrent refreshes with the same token succeed within grace.

        The frontend interceptors have no single-flight mutex: on
        access-token expiry, parallel 401 retries all present the same
        refresh token. The second presentation lands inside the
        rotation-grace window and must NOT nuke the family.
        """
        tokens = JWTManager.create_token_pair(self.user)
        old_refresh = tokens["refresh_token"]

        first = JWTManager.refresh_access_token(old_refresh)
        self.assertIsNotNone(first)

        # Simulated concurrent retry, immediately after rotation
        second = JWTManager.refresh_access_token(old_refresh)
        self.assertIsNotNone(second)
        self.assertIn("access_token", second)
        self.assertIn("refresh_token", second)

        # Both successors are live, in the original family
        for result in (first, second):
            db = RefreshToken.objects.get(
                token=RefreshToken.hash_token(result["refresh_token"])
            )
            self.assertFalse(db.is_revoked)

        # And the grace window does not slide: the anchor stays at the
        # original rotation timestamp
        old_db = RefreshToken.objects.get(
            token=RefreshToken.hash_token(old_refresh)
        )
        anchor = old_db.last_used
        JWTManager.refresh_access_token(old_refresh)
        old_db.refresh_from_db()
        self.assertEqual(old_db.last_used, anchor)

    def test_revoke_refresh_token(self):
        """Test revoking a refresh token."""
        tokens = JWTManager.create_token_pair(self.user)
        refresh_token = tokens["refresh_token"]

        # Revoke the token
        result = JWTManager.revoke_refresh_token(refresh_token)
        self.assertTrue(result)

        # Check that token is revoked in database
        db_token = RefreshToken.objects.get(
            token=RefreshToken.hash_token(refresh_token)
        )
        self.assertTrue(db_token.is_revoked)

    def test_revoke_nonexistent_token(self):
        """Test revoking a non-existent token."""
        result = JWTManager.revoke_refresh_token("nonexistent_token")
        self.assertFalse(result)

    def test_revoke_all_user_tokens(self):
        """Test revoking all user's refresh tokens."""
        # Create multiple token pairs
        for _ in range(3):
            JWTManager.create_token_pair(self.user)

        # Revoke all tokens
        count = JWTManager.revoke_all_user_tokens(self.user)
        self.assertEqual(count, 3)

        # Check that all tokens are revoked
        active_tokens = RefreshToken.objects.filter(
            user=self.user, is_revoked=False
        ).count()
        self.assertEqual(active_tokens, 0)
