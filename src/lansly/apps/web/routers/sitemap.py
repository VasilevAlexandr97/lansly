from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter
from fastapi.responses import Response

from lansly.apps.web.sitemap.builder import SitemapBuilder

router = APIRouter()


@router.get("/sitemap.xml", response_class=Response)
@inject
async def sitemap(builder: FromDishka[SitemapBuilder]):
    sitemap_xml = await builder.build()
    return Response(
        content=sitemap_xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )
