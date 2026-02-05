from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Optional

from azure.storage.blob import BlobServiceClient, ContentSettings
from beartype import beartype
from dotenv import load_dotenv


@beartype
def load_env(env_path: str | Path = ".env") -> None:
    """Load environment variables from a .env file (if present).

    Args:
        env_path: Path to a .env file. Defaults to ".env".

    Returns:
        None
    """
    load_dotenv(dotenv_path=Path(env_path), override=False)


@beartype
def _get_env(name: str) -> str:
    """Read an environment variable, raising if missing."""
    v = os.getenv(name)
    if not v:
        raise ValueError(f"Missing env var: {name}")
    return v


@beartype
def get_container_name() -> str:
    """Get target Azure container name.

    Returns:
        Container name. Defaults to "stability-images".
    """
    return os.getenv("AZURE_CONTAINER_NAME", "stability-images")


@beartype
def get_cdn_base_url() -> str:
    """Get CDN base URL for constructing public URLs.

    Returns:
        CDN base URL. Defaults to "https://content.dashtoon.ai".
    """
    return os.getenv("AZURE_CDN_BASE_URL", "https://content.dashtoon.ai").rstrip("/")


@beartype
def build_cdn_url(*, container: str, blob_name: str) -> str:
    """Build the public CDN URL for an uploaded blob.

    Args:
        container: Azure container name.
        blob_name: Blob name/path inside the container.

    Returns:
        Public CDN URL.
    """
    return f"{get_cdn_base_url()}/{container}/{blob_name.lstrip('/')}"


@beartype
def get_blob_service_client() -> BlobServiceClient:
    """Create an Azure BlobServiceClient.

    Supports two auth patterns used across our scripts:
    - Connection string only (AZURE_STORAGE_CONNECTION_STRING)
    - Connection string + SAS token appended (AZURE_STORAGE_SAS_TOKEN)

    Returns:
        BlobServiceClient
    """
    connection_string = _get_env("AZURE_STORAGE_CONNECTION_STRING")
    sas_token = os.getenv("AZURE_STORAGE_SAS_TOKEN")

    if sas_token:
        # Matches existing tooling patterns that do:
        # BlobServiceClient(f"{connection_string}?{sas_token}")
        return BlobServiceClient(f"{connection_string}?{sas_token}")

    return BlobServiceClient.from_connection_string(connection_string)


@beartype
def upload_bytes_to_azure(
    *,
    data: bytes,
    blob_name: str,
    container: Optional[str] = None,
    content_type: Optional[str] = None,
    cache_control: str = "public, max-age=31536000",
    overwrite: bool = True,
    timeout_s: int = 300,
) -> str:
    """Upload raw bytes to Azure Blob Storage and return a CDN URL.

    Args:
        data: Raw bytes to upload.
        blob_name: Blob name/path inside container (e.g. "exp1/out.mp4").
        container: Azure container name. Defaults to env AZURE_CONTAINER_NAME or "stability-images".
        content_type: MIME type (e.g. "image/png"). Optional.
        cache_control: Cache-Control header. Defaults to 1 year.
        overwrite: Whether to overwrite existing blobs. Defaults to True.
        timeout_s: Upload timeout in seconds.

    Returns:
        Public CDN URL for the uploaded blob.
    """
    container = container or get_container_name()

    bs = get_blob_service_client()
    container_client = bs.get_container_client(container)
    blob_client = container_client.get_blob_client(blob_name)

    content_settings: ContentSettings | None = None
    if content_type or cache_control:
        content_settings = ContentSettings(content_type=content_type, cache_control=cache_control)

    blob_client.upload_blob(
        data,
        overwrite=overwrite,
        timeout=timeout_s,
        content_settings=content_settings,
    )

    return build_cdn_url(container=container, blob_name=blob_name)


@beartype
def upload_file_to_azure(
    *,
    local_path: str | Path,
    blob_name: Optional[str] = None,
    container: Optional[str] = None,
    content_type: Optional[str] = None,
    cache_control: str = "public, max-age=31536000",
    overwrite: bool = True,
    timeout_s: int = 300,
) -> str:
    """Upload a local file (image/video/json/anything) to Azure and return a CDN URL.

    Args:
        local_path: Path to the file on disk.
        blob_name: Blob name/path inside container. Defaults to the file name.
        container: Azure container name. Defaults to env AZURE_CONTAINER_NAME or "stability-images".
        content_type: MIME type override. If not provided, guessed from filename.
        cache_control: Cache-Control header. Defaults to 1 year.
        overwrite: Whether to overwrite existing blobs. Defaults to True.
        timeout_s: Upload timeout in seconds.

    Returns:
        Public CDN URL for the uploaded blob.
    """
    p = Path(local_path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    blob_name = blob_name or p.name

    if not content_type:
        content_type, _ = mimetypes.guess_type(str(p))

    return upload_bytes_to_azure(
        data=p.read_bytes(),
        blob_name=blob_name,
        container=container,
        content_type=content_type,
        cache_control=cache_control,
        overwrite=overwrite,
        timeout_s=timeout_s,
    )


@beartype
def upload_json_file_to_azure(
    *,
    json_file_path: str | Path,
    blob_name: Optional[str] = None,
    container: Optional[str] = None,
) -> str:
    """Upload a JSON file to Azure with correct content-type and return a CDN URL.

    Args:
        json_file_path: Path to a .json file.
        blob_name: Blob name/path inside container. Defaults to "<stem>.json".
        container: Azure container name. Defaults to env AZURE_CONTAINER_NAME or "stability-images".

    Returns:
        Public CDN URL for the uploaded blob.
    """
    p = Path(json_file_path)
    blob_name = blob_name or f"{p.stem}.json"
    if not blob_name.endswith(".json"):
        blob_name = f"{blob_name}.json"
    return upload_file_to_azure(
        local_path=p,
        blob_name=blob_name,
        container=container,
        content_type="application/json",
        cache_control="public, max-age=31536000",
    )


if __name__ == "__main__":
    # Minimal CLI for quick manual testing:
    #   python upload_file_to_azure.py path/to/file.ext [blob_name]
    import sys

    load_env()

    if len(sys.argv) < 2:
        print("Usage: python upload_file_to_azure.py <local_path> [blob_name]")
        raise SystemExit(1)

    local_path_arg = sys.argv[1]
    blob_name_arg = sys.argv[2] if len(sys.argv) > 2 else None
    print(upload_file_to_azure(local_path=local_path_arg, blob_name=blob_name_arg))

