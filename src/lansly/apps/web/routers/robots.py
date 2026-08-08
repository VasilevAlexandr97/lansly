from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

ROBOTS_TXT = """User-agent: *
Allow: /

Host: https://lansly.ru/
Sitemap: https://lansly.ru/sitemap.xml
"""


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return ROBOTS_TXT
