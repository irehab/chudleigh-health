"""How the portal is served (the Dockerfile runs `streamlit run serve.py`): the app in app.py, plus one header on every reply.

X-Robots-Tag: noindex tells search engines not to list any page of the portal. It is a header rather than a robots.txt
"Disallow", because a search engine has to be allowed to fetch a page to see that it must not list it.
"""
import streamlit as st
from starlette.middleware import Middleware

NO_INDEX = (b"x-robots-tag", b"noindex, nofollow")


class NoIndexMiddleware:
    """Adds X-Robots-Tag: noindex, nofollow to every HTTP response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), NO_INDEX]
            await send(message)

        await self.app(scope, receive, send_with_header)


app = st.App("app.py", middleware=[Middleware(NoIndexMiddleware)])
