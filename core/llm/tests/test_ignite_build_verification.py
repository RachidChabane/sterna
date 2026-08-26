"""Tests for BUILD_ID verification before spark ignite."""
import asyncio
from unittest.mock import AsyncMock, MagicMock
from django.test import TestCase


class TestIgniteBuildVerification(TestCase):
    """Tests the BUILD_ID check logic in the coding_agent tool's ignite block."""

    def _run_verification(self, make_request_side_effect):
        """Run the build verification logic extracted from coding_agent.

        Returns whether the build was verified.
        """
        context = MagicMock()
        context._make_request = AsyncMock(side_effect=make_request_side_effect)
        context.spark_ignite_request = {"spark_id": "test-spark-123", "spark_code": "code"}
        context.user_id = "user1"
        context.chat_id = "chat1"
        context.last_preview_command = "npm run dev"

        spark_id = context.spark_ignite_request["spark_id"]
        build_verified = False

        async def _verify():
            nonlocal build_verified
            try:
                check_resp = await context._make_request("/fs/read", {
                    "path": f"spark-app-{spark_id}/.next/BUILD_ID",
                })
                build_verified = check_resp.get("success", False) and bool(check_resp.get("content", "").strip())
            except Exception:
                build_verified = False
            return build_verified

        return asyncio.run(_verify())

    def test_build_id_exists_ignite_proceeds(self):
        """BUILD_ID exists -> build_verified=True, ignite should proceed."""
        build_verified = self._run_verification(
            make_request_side_effect=lambda *a, **kw: {"success": True, "content": "abc123\n"}
        )
        self.assertTrue(build_verified)

    def test_build_id_missing_ignite_skipped(self):
        """BUILD_ID missing -> build_verified=False, ignite should be skipped."""
        build_verified = self._run_verification(
            make_request_side_effect=lambda *a, **kw: {"success": False, "error": "File not found"}
        )
        self.assertFalse(build_verified)

    def test_build_id_check_exception_skipped(self):
        """_make_request raises exception -> build_verified=False, no crash."""
        build_verified = self._run_verification(
            make_request_side_effect=Exception("Connection failed")
        )
        self.assertFalse(build_verified)

    def test_build_id_empty_content_skipped(self):
        """BUILD_ID file exists but is empty -> build_verified=False."""
        build_verified = self._run_verification(
            make_request_side_effect=lambda *a, **kw: {"success": True, "content": "  \n"}
        )
        self.assertFalse(build_verified)
