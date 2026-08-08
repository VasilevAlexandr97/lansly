from lansly.articles.consts import (
    FILENAME_MAX_LENGTH,
    IMAGE_MAGIC_SIGNATURES,
    MAX_IMAGE_BYTES,
    ArticleImageContentType,
)
from lansly.articles.dto import ArticleImageFileData
from lansly.articles.exceptions import InvalidArticleImageError


def article_image_validator(file: ArticleImageFileData):
    if file.content_type not in ArticleImageContentType:
        raise InvalidArticleImageError(
            f"Invalid file type: {file.content_type}",
        )
    if len(file.data) > MAX_IMAGE_BYTES:
        raise InvalidArticleImageError("File large then 5mb")
    if len(file.filename) > FILENAME_MAX_LENGTH:
        raise InvalidArticleImageError("File filename length error")

    signature, offset = IMAGE_MAGIC_SIGNATURES.get(
        file.content_type,
        (None, 0),
    )
    if (
        signature is None
        or file.data[offset : offset + len(signature)] != signature
    ):
        raise InvalidArticleImageError(
            "File content does not match declared type",
        )



