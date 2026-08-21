"""
Tests for user isolation in the preferences service.

These tests verify that:
1. Users can only access their own preferences
2. Users cannot see other users' preferences
3. Users cannot modify other users' preferences
4. Users cannot delete other users' preferences
5. Authentication is properly enforced
"""

from fastapi.testclient import TestClient

from .conftest import get_auth_headers


class TestUserIsolation:
    """Test suite for user data isolation."""

    def test_user_can_create_own_preference(self, client: TestClient, user_a_token: str):
        """Test that a user can create their own preference."""
        response = client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "dark", "category": "ui"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["preference_key"] == "ui.theme"
        assert data["preference_value"] == "dark"
        assert data["category"] == "ui"

    def test_user_can_read_own_preference(self, client: TestClient, user_a_token: str):
        """Test that a user can read their own preference."""
        # Create preference
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "dark", "category": "ui"},
        )

        # Read preference
        response = client.get(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["preference_key"] == "ui.theme"
        assert data["preference_value"] == "dark"

    def test_user_cannot_see_other_users_preferences(
        self, client: TestClient, user_a_token: str, user_b_token: str
    ):
        """
        CRITICAL ISOLATION TEST:
        Verify that User A cannot see User B's preferences.
        """
        # User A creates a preference
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "dark", "category": "ui"},
        )

        # User B creates a different preference
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_b_token),
            json={"preference_value": "light", "category": "ui"},
        )

        # User A should only see their own preference (dark)
        response = client.get(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
        )
        assert response.status_code == 200
        assert response.json()["preference_value"] == "dark"

        # User B should only see their own preference (light)
        response = client.get(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_b_token),
        )
        assert response.status_code == 200
        assert response.json()["preference_value"] == "light"

    def test_user_list_preferences_only_shows_own(
        self, client: TestClient, user_a_token: str, user_b_token: str
    ):
        """
        CRITICAL ISOLATION TEST:
        Verify that listing preferences only returns the authenticated user's data.
        """
        # User A creates multiple preferences
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "dark", "category": "ui"},
        )
        client.put(
            "/api/v1/preferences/ui.sidebar",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "collapsed", "category": "ui"},
        )

        # User B creates multiple preferences
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_b_token),
            json={"preference_value": "light", "category": "ui"},
        )
        client.put(
            "/api/v1/preferences/models.favorite",
            headers=get_auth_headers(user_b_token),
            json={"preference_value": "gpt-4", "category": "models"},
        )

        # User A should only see 2 preferences (their own)
        response = client.get(
            "/api/v1/preferences",
            headers=get_auth_headers(user_a_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert "ui.theme" in data["preferences"]
        assert "ui.sidebar" in data["preferences"]
        assert data["preferences"]["ui.theme"] == "dark"
        assert "models.favorite" not in data["preferences"]

        # User B should only see 2 preferences (their own)
        response = client.get(
            "/api/v1/preferences",
            headers=get_auth_headers(user_b_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert "ui.theme" in data["preferences"]
        assert "models.favorite" in data["preferences"]
        assert data["preferences"]["ui.theme"] == "light"
        assert "ui.sidebar" not in data["preferences"]

    def test_user_cannot_modify_other_users_preferences_indirectly(
        self, client: TestClient, user_a_token: str, user_b_token: str
    ):
        """
        CRITICAL ISOLATION TEST:
        Verify that User A modifying a preference doesn't affect User B's same key.
        """
        # User A creates preference
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "dark", "category": "ui"},
        )

        # User B creates same preference key with different value
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_b_token),
            json={"preference_value": "light", "category": "ui"},
        )

        # User A updates their preference
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "blue", "category": "ui"},
        )

        # Verify User B's preference is unchanged
        response = client.get(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_b_token),
        )
        assert response.status_code == 200
        assert response.json()["preference_value"] == "light"

    def test_user_cannot_delete_other_users_preferences_indirectly(
        self, client: TestClient, user_a_token: str, user_b_token: str
    ):
        """
        CRITICAL ISOLATION TEST:
        Verify that User A deleting a preference doesn't affect User B's same key.
        """
        # Both users create the same preference key
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "dark", "category": "ui"},
        )
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_b_token),
            json={"preference_value": "light", "category": "ui"},
        )

        # User A deletes their preference
        response = client.delete(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
        )
        assert response.status_code == 200

        # Verify User A's preference is deleted
        response = client.get(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
        )
        assert response.status_code == 404

        # Verify User B's preference still exists
        response = client.get(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_b_token),
        )
        assert response.status_code == 200
        assert response.json()["preference_value"] == "light"

    def test_bulk_update_only_affects_own_preferences(
        self, client: TestClient, user_a_token: str, user_b_token: str
    ):
        """
        CRITICAL ISOLATION TEST:
        Verify bulk updates only affect the authenticated user's preferences.
        """
        # User A creates initial preferences
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "dark", "category": "ui"},
        )

        # User B creates preferences
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_b_token),
            json={"preference_value": "light", "category": "ui"},
        )
        client.put(
            "/api/v1/preferences/ui.sidebar",
            headers=get_auth_headers(user_b_token),
            json={"preference_value": "expanded", "category": "ui"},
        )

        # User A does bulk update
        response = client.put(
            "/api/v1/preferences",
            headers=get_auth_headers(user_a_token),
            json={
                "preferences": {
                    "ui.theme": "blue",
                    "ui.sidebar": "collapsed",
                    "models.favorite": "claude-3",
                }
            },
        )
        assert response.status_code == 200

        # Verify User B's preferences are unchanged
        response = client.get(
            "/api/v1/preferences",
            headers=get_auth_headers(user_b_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["preferences"]["ui.theme"] == "light"
        assert data["preferences"]["ui.sidebar"] == "expanded"
        assert "models.favorite" not in data["preferences"]

        # Verify User A has new preferences
        response = client.get(
            "/api/v1/preferences",
            headers=get_auth_headers(user_a_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["preferences"]["ui.theme"] == "blue"
        assert data["preferences"]["ui.sidebar"] == "collapsed"
        assert data["preferences"]["models.favorite"] == "claude-3"


class TestAuthentication:
    """Test suite for authentication enforcement."""

    def test_missing_token_returns_403(self, client: TestClient):
        """Test that requests without a token are rejected."""
        response = client.get("/api/v1/preferences")
        assert response.status_code == 403

    def test_invalid_token_returns_401(self, client: TestClient, invalid_token: str):
        """Test that invalid tokens are rejected."""
        response = client.get(
            "/api/v1/preferences",
            headers=get_auth_headers(invalid_token),
        )
        assert response.status_code == 401

    def test_expired_token_returns_401(self, client: TestClient, expired_token: str):
        """Test that expired tokens are rejected."""
        response = client.get(
            "/api/v1/preferences",
            headers=get_auth_headers(expired_token),
        )
        assert response.status_code == 401

    def test_all_endpoints_require_authentication(
        self, client: TestClient, user_a_token: str
    ):
        """Test that all endpoints require valid authentication."""
        # First create a preference with valid auth
        client.put(
            "/api/v1/preferences/test.key",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "test", "category": "test"},
        )

        # Test all endpoints without auth
        endpoints = [
            ("GET", "/api/v1/preferences"),
            ("GET", "/api/v1/preferences/test.key"),
            ("PUT", "/api/v1/preferences/test.key"),
            ("PUT", "/api/v1/preferences"),
            ("DELETE", "/api/v1/preferences/test.key"),
        ]

        for method, url in endpoints:
            if method == "GET":
                response = client.get(url)
            elif method == "PUT":
                response = client.put(url, json={"preference_value": "test"})
            elif method == "DELETE":
                response = client.delete(url)

            assert response.status_code in [401, 403], (
                f"{method} {url} should require authentication, "
                f"got {response.status_code}"
            )


class TestCategoryFiltering:
    """Test suite for category filtering with user isolation."""

    def test_category_filter_respects_user_isolation(
        self, client: TestClient, user_a_token: str, user_b_token: str
    ):
        """
        CRITICAL ISOLATION TEST:
        Verify category filtering only returns the authenticated user's preferences.
        """
        # User A creates preferences in different categories
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "dark", "category": "ui"},
        )
        client.put(
            "/api/v1/preferences/models.favorite",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": "gpt-4", "category": "models"},
        )

        # User B creates preferences in the same categories
        client.put(
            "/api/v1/preferences/ui.theme",
            headers=get_auth_headers(user_b_token),
            json={"preference_value": "light", "category": "ui"},
        )
        client.put(
            "/api/v1/preferences/ui.sidebar",
            headers=get_auth_headers(user_b_token),
            json={"preference_value": "expanded", "category": "ui"},
        )

        # User A filters by 'ui' category - should only see their preference
        response = client.get(
            "/api/v1/preferences?category=ui",
            headers=get_auth_headers(user_a_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert "ui.theme" in data["preferences"]
        assert data["preferences"]["ui.theme"] == "dark"
        assert "ui.sidebar" not in data["preferences"]

        # User B filters by 'ui' category - should see 2 of their preferences
        response = client.get(
            "/api/v1/preferences?category=ui",
            headers=get_auth_headers(user_b_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert "ui.theme" in data["preferences"]
        assert "ui.sidebar" in data["preferences"]
        assert data["preferences"]["ui.theme"] == "light"


class TestComplexDataTypes:
    """Test user isolation with complex JSON data types."""

    def test_isolation_with_array_values(
        self, client: TestClient, user_a_token: str, user_b_token: str
    ):
        """Test isolation works correctly with array preference values."""
        # User A sets favorite models
        client.put(
            "/api/v1/preferences/models.favorites",
            headers=get_auth_headers(user_a_token),
            json={"preference_value": ["gpt-4", "claude-3"], "category": "models"},
        )

        # User B sets different favorite models
        client.put(
            "/api/v1/preferences/models.favorites",
            headers=get_auth_headers(user_b_token),
            json={
                "preference_value": ["gemini-pro", "llama-2"],
                "category": "models",
            },
        )

        # Verify isolation
        response = client.get(
            "/api/v1/preferences/models.favorites",
            headers=get_auth_headers(user_a_token),
        )
        assert response.status_code == 200
        assert response.json()["preference_value"] == ["gpt-4", "claude-3"]

        response = client.get(
            "/api/v1/preferences/models.favorites",
            headers=get_auth_headers(user_b_token),
        )
        assert response.status_code == 200
        assert response.json()["preference_value"] == ["gemini-pro", "llama-2"]

    def test_isolation_with_object_values(
        self, client: TestClient, user_a_token: str, user_b_token: str
    ):
        """Test isolation works correctly with object preference values."""
        # User A sets navigation config
        client.put(
            "/api/v1/preferences/ui.navigation",
            headers=get_auth_headers(user_a_token),
            json={
                "preference_value": {"order": ["home", "models", "settings"], "pinned": True},
                "category": "ui",
            },
        )

        # User B sets different navigation config
        client.put(
            "/api/v1/preferences/ui.navigation",
            headers=get_auth_headers(user_b_token),
            json={
                "preference_value": {"order": ["settings", "home"], "pinned": False},
                "category": "ui",
            },
        )

        # Verify isolation
        response = client.get(
            "/api/v1/preferences/ui.navigation",
            headers=get_auth_headers(user_a_token),
        )
        assert response.status_code == 200
        data = response.json()["preference_value"]
        assert data["order"] == ["home", "models", "settings"]
        assert data["pinned"] is True

        response = client.get(
            "/api/v1/preferences/ui.navigation",
            headers=get_auth_headers(user_b_token),
        )
        assert response.status_code == 200
        data = response.json()["preference_value"]
        assert data["order"] == ["settings", "home"]
        assert data["pinned"] is False
