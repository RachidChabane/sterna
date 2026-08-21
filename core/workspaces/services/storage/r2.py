"""Cloudflare R2 storage backend (S3-compatible)."""
import logging
from typing import Optional

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .base import StorageBackend

logger = logging.getLogger(__name__)


class R2Storage(StorageBackend):
    """
    Cloudflare R2 storage backend.

    R2 is S3-compatible, so we use aioboto3 with custom endpoint URL.
    Used for storing large workspace files (>256KB).
    """

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        endpoint_url: Optional[str] = None,
    ):
        """
        Initialize R2 storage.

        Args:
            account_id: Cloudflare account ID (used to construct endpoint if not provided)
            access_key_id: R2 access key ID
            secret_access_key: R2 secret access key
            bucket: R2 bucket name
            endpoint_url: Optional custom endpoint (for MinIO compatibility in dev)
        """
        self.endpoint_url = endpoint_url or f"https://{account_id}.r2.cloudflarestorage.com"
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.bucket = bucket
        self._session = aioboto3.Session()

    def _get_client_kwargs(self) -> dict:
        """Get kwargs for boto3 client."""
        return {
            "service_name": "s3",
            "endpoint_url": self.endpoint_url,
            "aws_access_key_id": self.access_key_id,
            "aws_secret_access_key": self.secret_access_key,
            "config": Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        }

    async def upload(
        self,
        key: str,
        content: bytes,
        content_type: Optional[str] = None
    ) -> str:
        """
        Upload content to R2.

        Args:
            key: Object key (path in bucket)
            content: Binary content to upload
            content_type: Optional MIME type

        Returns:
            The object key
        """
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        async with self._session.client(**self._get_client_kwargs()) as client:
            await client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                **extra_args,
            )

        logger.debug(f"Uploaded {len(content)} bytes to R2: {key}")
        return key

    async def download(self, key: str) -> bytes:
        """
        Download content from R2.

        Args:
            key: Object key to download

        Returns:
            Binary content

        Raises:
            FileNotFoundError: If object doesn't exist
        """
        try:
            async with self._session.client(**self._get_client_kwargs()) as client:
                response = await client.get_object(Bucket=self.bucket, Key=key)
                content = await response["Body"].read()

            logger.debug(f"Downloaded {len(content)} bytes from R2: {key}")
            return content
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"Object not found: {key}")
            raise

    async def delete(self, key: str) -> bool:
        """
        Delete object from R2.

        Args:
            key: Object key to delete

        Returns:
            True if deletion was successful
        """
        try:
            async with self._session.client(**self._get_client_kwargs()) as client:
                await client.delete_object(Bucket=self.bucket, Key=key)
            logger.debug(f"Deleted from R2: {key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete from R2: {key} - {e}")
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if object exists in R2.

        Args:
            key: Object key to check

        Returns:
            True if object exists
        """
        try:
            async with self._session.client(**self._get_client_kwargs()) as client:
                await client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    async def get_presigned_url(
        self,
        key: str,
        expiration: int = 3600,
        method: str = "get_object"
    ) -> str:
        """
        Generate a presigned URL for direct access.

        Args:
            key: Object key
            expiration: URL expiration in seconds (default 1 hour)
            method: S3 method ('get_object' for download, 'put_object' for upload)

        Returns:
            Presigned URL string
        """
        async with self._session.client(**self._get_client_kwargs()) as client:
            url = await client.generate_presigned_url(
                method,
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expiration,
            )
        return url

    async def list_objects(self, prefix: str = "") -> list[dict]:
        """
        List objects with given prefix.

        Args:
            prefix: Key prefix to filter by

        Returns:
            List of object metadata dicts
        """
        objects = []
        async with self._session.client(**self._get_client_kwargs()) as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    objects.append({
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"],
                    })
        return objects

    async def copy_object(self, source_key: str, dest_key: str) -> bool:
        """
        Copy an object within the bucket.

        Args:
            source_key: Source object key
            dest_key: Destination object key

        Returns:
            True if copy was successful
        """
        try:
            async with self._session.client(**self._get_client_kwargs()) as client:
                await client.copy_object(
                    Bucket=self.bucket,
                    CopySource={"Bucket": self.bucket, "Key": source_key},
                    Key=dest_key,
                )
            logger.debug(f"Copied R2 object: {source_key} -> {dest_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to copy R2 object: {source_key} -> {dest_key} - {e}")
            return False
