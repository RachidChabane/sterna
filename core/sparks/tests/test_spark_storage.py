"""Spark R2 storage round-trip.

Covers the inline/R2 split in Spark.save_code()/get_code(): an
over-threshold spark must upload and read back through the same R2
key, an under-threshold spark must never touch the network, and an
R2 upload failure must not lose the code. The R2 client is mocked at
the boto3 adapter seam (put_object/get_object); everything above that
(WorkspaceStorageService, Spark) runs for real.
"""
import io

from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from django.test import TestCase, override_settings
from unittest.mock import patch

from authentication.models import User
from conversations.models import Chat, Conversation
from sparks.models import Spark
from workspaces.services.workspace_storage import WorkspaceStorageService


class FakeR2Client:
    """In-memory stand-in for the boto3 S3 client, keyed like real R2."""

    def __init__(self, fail_put: bool = False):
        self.fail_put = fail_put
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[str] = []

    def put_object(self, Bucket, Key, Body, **kwargs):
        if self.fail_put:
            raise ClientError({"Error": {"Code": "InternalError"}}, "PutObject")
        self.put_calls.append(Key)
        self.objects[Key] = bytes(Body)

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}


class SparkStorageTest(TestCase):
    def setUp(self):
        WorkspaceStorageService._instance = None
        WorkspaceStorageService._r2_client = None

        self.user = User.objects.create_user(
            email="spark-owner@example.com", password="x" * 12
        )
        conversation = Conversation.objects.create(user=self.user)
        self.chat = Chat.objects.create(conversation=conversation)

    def tearDown(self):
        WorkspaceStorageService._instance = None
        WorkspaceStorageService._r2_client = None

    def _make_spark(self, chat=None):
        return Spark.objects.create(
            user=self.user,
            chat=chat,
            title="Test Spark",
            framework=Spark.Framework.REACT,
        )

    @override_settings(SPARK_INLINE_THRESHOLD=10)
    def test_oversized_spark_with_chat_round_trips_through_r2(self):
        fake_client = FakeR2Client()
        code = "export default function App() { return <div>hi</div>; }"
        spark = self._make_spark(chat=self.chat)

        with patch.object(
            WorkspaceStorageService, "_get_r2_client", return_value=fake_client
        ):
            spark.save_code(code)
            spark.save()

            self.assertEqual(spark.storage_type, Spark.StorageType.R2)
            self.assertTrue(spark.r2_key)
            self.assertEqual(fake_client.put_calls, [spark.r2_key])

            reloaded = Spark.objects.get(pk=spark.pk)
            self.assertEqual(reloaded.storage_type, Spark.StorageType.R2)
            self.assertEqual(reloaded.get_code(), code)

    @override_settings(SPARK_INLINE_THRESHOLD=10)
    def test_oversized_spark_without_chat_round_trips_through_r2(self):
        fake_client = FakeR2Client()
        code = "export default function App() { return <div>no chat</div>; }"
        spark = self._make_spark(chat=None)

        with patch.object(
            WorkspaceStorageService, "_get_r2_client", return_value=fake_client
        ):
            spark.save_code(code)
            spark.save()

            reloaded = Spark.objects.get(pk=spark.pk)
            self.assertEqual(reloaded.storage_type, Spark.StorageType.R2)
            self.assertEqual(reloaded.get_code(), code)

    def test_small_spark_stays_inline_and_never_touches_r2(self):
        fake_client = FakeR2Client()
        code = "export default () => null;"
        spark = self._make_spark(chat=self.chat)

        with patch.object(
            WorkspaceStorageService, "_get_r2_client", return_value=fake_client
        ):
            spark.save_code(code)
            spark.save()

            self.assertEqual(spark.storage_type, Spark.StorageType.INLINE)
            self.assertEqual(spark.r2_key, "")
            self.assertEqual(spark.get_code(), code)
            self.assertEqual(fake_client.put_calls, [])

    @override_settings(SPARK_INLINE_THRESHOLD=10)
    def test_r2_upload_failure_falls_back_to_inline(self):
        fake_client = FakeR2Client(fail_put=True)
        code = "export default function App() { return <div>fallback</div>; }"
        spark = self._make_spark(chat=self.chat)

        with patch.object(
            WorkspaceStorageService, "_get_r2_client", return_value=fake_client
        ):
            spark.save_code(code)

            self.assertEqual(spark.storage_type, Spark.StorageType.INLINE)
            self.assertEqual(spark.code, code)
            self.assertEqual(spark.r2_key, "")
            self.assertEqual(spark.get_code(), code)
