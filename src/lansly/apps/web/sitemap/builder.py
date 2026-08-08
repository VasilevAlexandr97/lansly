import xml.etree.ElementTree as ET

from lansly.apps.web.sitemap.schema import SitemapSection


class SitemapBuilder:
    def __init__(self, sections: list[SitemapSection]):
        self.sections = sections

    async def build(self) -> str:
        urlset = ET.Element(
            "urlset",
            {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"},
        )
        for section in self.sections:
            for entry in await section.entries():
                url = ET.SubElement(urlset, "url")
                ET.SubElement(url, "loc").text = entry.loc
                if entry.lastmod is not None:
                    ET.SubElement(
                        url,
                        "lastmod",
                    ).text = entry.lastmod.strftime("%Y-%m-%d")
                if entry.changefreq is not None:
                    ET.SubElement(url, "changefreq").text = entry.changefreq
                if entry.priority is not None:
                    ET.SubElement(url, "priority").text = str(entry.priority)
        ET.indent(urlset, space="  ")
        return ET.tostring(urlset, encoding="unicode", xml_declaration=True)
