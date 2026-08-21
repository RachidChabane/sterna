"""
Artifact Storage

Manages storage and retrieval of skill-generated artifacts using S3/MinIO.
Provides signed URLs for secure downloads.
"""

import os
import logging
from typing import List, Optional
import boto3
from botocore.exceptions import ClientError
from botocore.client import Config

logger = logging.getLogger(__name__)


class ArtifactStorage:
    """Manages artifact storage in S3/MinIO."""

    def __init__(self):
        """Initialize S3/MinIO client."""
        self.endpoint_url = os.getenv('S3_ENDPOINT_URL', 'http://minio:9000')
        self.access_key = os.getenv('S3_ACCESS_KEY', 'minioadmin')
        self.secret_key = os.getenv('S3_SECRET_KEY', 'minioadmin')
        self.bucket_name = os.getenv('S3_BUCKET', 'sterna-artifacts')
        self.region = os.getenv('S3_REGION', 'us-east-1')

        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(signature_version='s3v4')
        )

        # Ensure bucket exists
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket {self.bucket_name} exists")
        except ClientError:
            try:
                self.s3_client.create_bucket(Bucket=self.bucket_name)
                logger.info(f"Created bucket {self.bucket_name}")
            except ClientError as e:
                logger.error(f"Failed to create bucket: {e}")

    def _get_object_key(self, user_id: str, project_id: str, artifact_name: str) -> str:
        """
        Generate S3 object key for an artifact.

        Format: artifacts/{user_id}/{project_id}/{artifact_name}
        """
        return f"artifacts/{user_id}/{project_id}/{artifact_name}"

    async def upload_artifact(
        self,
        user_id: str,
        project_id: str,
        artifact_name: str,
        local_path: str
    ) -> str:
        """
        Upload an artifact file to S3/MinIO.

        Args:
            user_id: User identifier
            project_id: Project identifier
            artifact_name: Name of the artifact
            local_path: Local file path to upload

        Returns:
            S3 object key (not a full URL for security)
        """
        object_key = self._get_object_key(user_id, project_id, artifact_name)

        try:
            # Detect content type
            import mimetypes
            content_type, _ = mimetypes.guess_type(local_path)

            # Upload file
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type

            self.s3_client.upload_file(
                local_path,
                self.bucket_name,
                object_key,
                ExtraArgs=extra_args
            )

            logger.info(f"Uploaded artifact: {object_key}")
            return object_key

        except ClientError as e:
            logger.error(f"Failed to upload artifact {object_key}: {e}")
            raise

    async def get_download_url(
        self,
        user_id: str,
        project_id: str,
        artifact_name: str,
        expiration: int = 3600
    ) -> str:
        """
        Generate a presigned URL for downloading an artifact.

        Args:
            user_id: User identifier
            project_id: Project identifier
            artifact_name: Name of the artifact
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned download URL
        """
        object_key = self._get_object_key(user_id, project_id, artifact_name)

        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': object_key
                },
                ExpiresIn=expiration
            )

            logger.info(f"Generated download URL for {object_key}")
            return url

        except ClientError as e:
            logger.error(f"Failed to generate URL for {object_key}: {e}")
            raise

    async def list_artifacts(
        self,
        user_id: str,
        project_id: str
    ) -> List[dict]:
        """
        List all artifacts for a user×project.

        Returns:
            List of artifact metadata dicts
        """
        prefix = f"artifacts/{user_id}/{project_id}/"

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            artifacts = []
            for obj in response.get('Contents', []):
                # Extract artifact name from key
                artifact_name = obj['Key'].replace(prefix, '')

                artifacts.append({
                    'name': artifact_name,
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat(),
                    'etag': obj['ETag'].strip('"')
                })

            return artifacts

        except ClientError as e:
            logger.error(f"Failed to list artifacts for {user_id}/{project_id}: {e}")
            return []

    async def delete_artifact(
        self,
        user_id: str,
        project_id: str,
        artifact_name: str
    ) -> bool:
        """
        Delete an artifact.

        Returns:
            True if successful
        """
        object_key = self._get_object_key(user_id, project_id, artifact_name)

        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=object_key
            )

            logger.info(f"Deleted artifact: {object_key}")
            return True

        except ClientError as e:
            logger.error(f"Failed to delete artifact {object_key}: {e}")
            return False

    async def delete_all_artifacts(
        self,
        user_id: str,
        project_id: str
    ) -> int:
        """
        Delete all artifacts for a user×project.

        Returns:
            Number of artifacts deleted
        """
        artifacts = await self.list_artifacts(user_id, project_id)

        count = 0
        for artifact in artifacts:
            if await self.delete_artifact(user_id, project_id, artifact['name']):
                count += 1

        logger.info(f"Deleted {count} artifacts for {user_id}/{project_id}")
        return count

    def get_artifact_metadata(
        self,
        user_id: str,
        project_id: str,
        artifact_name: str
    ) -> Optional[dict]:
        """
        Get metadata for a specific artifact.

        Returns:
            Metadata dict or None if not found
        """
        object_key = self._get_object_key(user_id, project_id, artifact_name)

        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=object_key
            )

            return {
                'name': artifact_name,
                'key': object_key,
                'size': response['ContentLength'],
                'last_modified': response['LastModified'].isoformat(),
                'content_type': response.get('ContentType'),
                'etag': response['ETag'].strip('"')
            }

        except ClientError:
            logger.warning(f"Artifact not found: {object_key}")
            return None
