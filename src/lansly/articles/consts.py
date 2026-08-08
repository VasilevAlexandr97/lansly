from enum import StrEnum


class ArticleImageContentType(StrEnum):
    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"
    GIF = "image/gif"


IMAGE_MAGIC_SIGNATURES: dict[str, tuple[bytes, int]] = {
    "image/jpeg": (b"\xff\xd8\xff", 0),  # FF D8 FF
    "image/png": (b"\x89PNG", 0),  # 89 50 4E 47
    "image/gif": (b"GIF8", 0),  # GIF87a/GIF89a
    "image/webp": (b"WEBP", 8),  # RIFF .... WEBP (offset 8)
}

MAX_IMAGE_BYTES = 5 * 1024 * 1024

FILENAME_MAX_LENGTH = 128
