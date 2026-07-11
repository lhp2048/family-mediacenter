from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class PrivateNetworkAccessMiddleware(BaseHTTPMiddleware):
    """Chrome Private Network Access: Web clients on public origin need this for LAN APIs."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.headers.get("access-control-request-private-network") == "true":
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        elif request.headers.get("origin"):
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response
