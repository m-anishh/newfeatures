"""
Storage Repository
Data access for file storage operations.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from pathlib import Path

from backend.database.db_client import get_db_client

from backend.core.logging import get_logger
from backend.core.exceptions import StorageError

logger = get_logger(__name__)


class StorageRepository:
    """
    Repository for file storage operations.
    
    Handles:
    - File uploads
    - File downloads
    - File deletions
    - Signed URL generation
    """
    
    def __init__(self):
        self._upload_bucket = "uploads"
        self._reports_bucket = "visionx-reports"
        self._thumbnails_bucket = "thumbnails"
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = get_db_client()
        return self._client
    
    async def upload(
        self,
        file: bytes,
        bucket: str,
        path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload file to storage.
        
        Args:
            file: File content as bytes
            bucket: Storage bucket name
            path: Storage path within bucket
            content_type: MIME type
            
        Returns:
            File URL or path
        """
        try:
            client = self._get_client()
            response = client.storage.from_(bucket).upload(path, file, file_options={"content-type": content_type})
            if hasattr(response, "path") and response.path:
                public_url = client.storage.from_(bucket).get_public_url(response.path)
                logger.info(f"Uploaded file to {bucket}/{path}")
                return public_url
            logger.info(f"Uploaded file to {bucket}/{path}")
            return f"https://{bucket}/{path}"
        except Exception as e:
            logger.error(f"Failed to upload file to {bucket}/{path}: {e}")
            raise StorageError(message=f"Failed to upload file: {e}") from e
    
    async def upload_file(
        self,
        file_path: Path,
        bucket: str,
        storage_path: str,
    ) -> str:
        """
        Upload file from filesystem.
        
        Args:
            file_path: Local file path
            bucket: Storage bucket name
            storage_path: Storage path within bucket
            
        Returns:
            File URL
        """
        try:
            content = Path(file_path).read_bytes()
            content_type = self._guess_content_type(file_path)
            return await self.upload(content, bucket, storage_path, content_type)
        except Exception as e:
            logger.error(f"Failed to upload file {file_path}: {e}")
            raise StorageError(message=f"Failed to upload file: {e}") from e
    
    async def download(self, bucket: str, path: str) -> bytes:
        """
        Download file from storage.
        
        Args:
            bucket: Storage bucket name
            path: Storage path
            
        Returns:
            File content as bytes
        """
        try:
            client = self._get_client()
            response = client.storage.from_(bucket).download(path)
            if hasattr(response, "content"):
                return response.content
            return response
        except Exception as e:
            logger.error(f"Failed to download file from {bucket}/{path}: {e}")
            raise StorageError(message=f"Failed to download file: {e}") from e
    
    async def delete(self, bucket: str, path: str) -> None:
        """
        Delete file from storage.
        
        Args:
            bucket: Storage bucket name
            path: Storage path
        """
        try:
            client = self._get_client()
            client.storage.from_(bucket).remove([path])
            logger.info(f"Deleted file from {bucket}/{path}")
        except Exception as e:
            logger.error(f"Failed to delete file from {bucket}/{path}: {e}")
            raise StorageError(message=f"Failed to delete file: {e}") from e
    
    async def get_url(self, bucket: str, path: str) -> str:
        """
        Get public URL for file.
        
        Args:
            bucket: Storage bucket name
            path: Storage path
            
        Returns:
            Public URL
        """
        try:
            client = self._get_client()
            return client.storage.from_(bucket).get_public_url(path)
        except Exception as e:
            logger.error(f"Failed to get URL for {bucket}/{path}: {e}")
            raise StorageError(message=f"Failed to get URL: {e}") from e
    
    async def get_signed_url(
        self,
        bucket: str,
        path: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        """
        Generate signed URL for private file.
        
        Args:
            bucket: Storage bucket name
            path: Storage path
            expires_in_seconds: URL expiration time
            
        Returns:
            Signed URL
        """
        try:
            client = self._get_client()
            return client.storage.from_(bucket).create_signed_url(path, expires_in_seconds)
        except Exception as e:
            logger.error(f"Failed to generate signed URL for {bucket}/{path}: {e}")
            raise StorageError(message=f"Failed to generate signed URL: {e}") from e
    
    async def list_files(
        self,
        bucket: str,
        path: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List files in bucket.
        
        Args:
            bucket: Storage bucket name
            path: Optional folder path
            limit: Maximum files to list
            
        Returns:
            List of file metadata
        """
        try:
            client = self._get_client()
            response = client.storage.from_(bucket).list(path or "")
            return response if isinstance(response, list) else []
        except Exception as e:
            logger.error(f"Failed to list files in {bucket}/{path}: {e}")
            raise StorageError(message=f"Failed to list files: {e}") from e
    
    def _guess_content_type(self, file_path: Path) -> str:
        """Guess MIME type from file extension."""
        extension_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
            ".txt": "text/plain",
        }
        return extension_map.get(file_path.suffix.lower(), "application/octet-stream")