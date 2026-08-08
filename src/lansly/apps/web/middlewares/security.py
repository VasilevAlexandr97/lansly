import logging
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

STS = "max-age=31536000; includeSubDomains"
XCTO = "nosniff"
XFO = "DENY"
RP = "strict-origin-when-cross-origin"
PP = "camera=(), microphone=(), geolocation=()"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        nonce = secrets.token_urlsafe()
        logger.debug(f"NONCE: {nonce}")
        request.state.nonce = nonce
        response: Response = await call_next(request)
        response.headers["Strict-Transport-Security"] = STS
        response.headers["X-Content-Type-Options"] = XCTO
        response.headers["X-Frame-Options"] = XFO
        response.headers["Referrer-Policy"] = RP
        response.headers["Permissions-Policy"] = PP
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'strict-dynamic' 'nonce-{nonce}' "
            "https://www.googletagmanager.com "
            "https://www.google-analytics.com "
            "https://mc.yandex.ru; "
            "style-src 'self' 'unsafe-inline' "
            "https://fonts.googleapis.com; "
            "font-src 'self' "
            "https://fonts.gstatic.com; "
            "img-src 'self' data: "
            "https://www.googletagmanager.com "
            "https://www.google-analytics.com "
            "https://ssl.google-analytics.com "
            "https://mc.yandex.ru; "
            "connect-src 'self' "
            "https://www.google-analytics.com "
            "https://analytics.google.com "
            "https://region1.google-analytics.com "
            "https://mc.yandex.ru "
            "wss://mc.yandex.ru; "
            "frame-src "
            "https://www.googletagmanager.com "
            "https://mc.yandex.ru; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none';"
        )
        return response
