import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP, Context
from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


APP_NAME = "Browser MCP for Claude"
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "true").lower() != "false"
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "").strip()
MAX_TEXT = int(os.getenv("MAX_PAGE_TEXT", "12000"))
ALLOWED_SCHEMES = {"http", "https"}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/healthz":
            return await call_next(request)
        if not MCP_AUTH_TOKEN:
            return JSONResponse({"error": "MCP_AUTH_TOKEN is not configured"}, status_code=503)
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {MCP_AUTH_TOKEN}"
        if not secrets.compare_digest(supplied, expected):
            return JSONResponse({"error": "Unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
        return await call_next(request)


class BrowserState:
    def __init__(self) -> None:
        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.lock = asyncio.Lock()

    async def ensure_page(self) -> Page:
        if self.page is None or self.page.is_closed():
            if self.context is None:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(headless=BROWSER_HEADLESS)
                self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
        return self.page

    async def close(self) -> None:
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None


state = BrowserState()
mcp = FastMCP(
    APP_NAME,
    instructions=(
        "Browser tools are for reviewing pages and filling forms. Never submit forms, purchase, "
        "send messages, delete data, or complete payments. Stop for user confirmation before any final action."
    ),
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8000")),
    streamable_http_path="/mcp",
    stateless_http=False,
)


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.netloc:
        raise ValueError("Only public http:// and https:// URLs are allowed")
    return url


def require_page() -> Page:
    if state.page is None or state.page.is_closed():
        raise RuntimeError("No page is open. Call browser_open first.")
    return state.page


async def interactive_snapshot(page: Page) -> list[dict[str, Any]]:
    return await page.locator("a,button,input,textarea,select,[role=button]").evaluate_all(
        """
        els => els.slice(0, 120).map((el, index) => ({
          ref: String(index),
          tag: el.tagName.toLowerCase(),
          type: el.getAttribute('type') || '',
          text: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim().slice(0, 180),
          name: el.getAttribute('name') || '',
          placeholder: el.getAttribute('placeholder') || '',
          value: el.tagName.toLowerCase() === 'input' || el.tagName.toLowerCase() === 'textarea' ? el.value : '',
          disabled: !!el.disabled
        }))
        """
    )


async def page_state(page: Page) -> dict[str, Any]:
    text = (await page.locator("body").inner_text())[:MAX_TEXT]
    controls = await interactive_snapshot(page)
    return {"url": page.url, "title": await page.title(), "text": text, "controls": controls}


@mcp.tool()
async def browser_open(url: str) -> dict[str, Any]:
    """Open a public HTTP(S) page and return readable text plus interactive control references."""
    validate_url(url)
    async with state.lock:
        page = await state.ensure_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(500)
        return await page_state(page)


@mcp.tool()
async def browser_snapshot() -> dict[str, Any]:
    """Read the current page and list safe interaction references; does not change the page."""
    return await page_state(require_page())


@mcp.tool()
async def browser_click(ref: str) -> dict[str, Any]:
    """Click a referenced non-submit control. Submit buttons and links are blocked for safety."""
    page = require_page()
    controls = await interactive_snapshot(page)
    index = int(ref)
    if index < 0 or index >= len(controls):
        raise ValueError("Unknown control reference")
    control = controls[index]
    text = f"{control.get('text', '')} {control.get('type', '')}".lower()
    blocked = {"submit", "send", "pay", "purchase", "checkout", "delete", "remove", "confirm", "book", "order"}
    if control.get("tag") == "button" and any(word in text for word in blocked):
        raise PermissionError("Final action blocked; ask the user to review and submit manually")
    if control.get("tag") == "a" and control.get("text", "").lower() in {"submit", "send", "pay", "checkout"}:
        raise PermissionError("Final action blocked; ask the user to review and submit manually")
    await page.locator("a,button,input,textarea,select,[role=button]").nth(index).click(timeout=15000)
    await page.wait_for_timeout(300)
    return await page_state(page)


@mcp.tool()
async def browser_fill(ref: str, value: str) -> dict[str, Any]:
    """Fill a text field. Password fields and hidden fields are blocked; final submission is never performed."""
    page = require_page()
    controls = await interactive_snapshot(page)
    index = int(ref)
    if index < 0 or index >= len(controls):
        raise ValueError("Unknown control reference")
    control = controls[index]
    if control.get("tag") not in {"input", "textarea"}:
        raise ValueError("Reference is not a text field")
    if control.get("type", "").lower() in {"password", "hidden", "file"}:
        raise PermissionError("Sensitive or file fields must be completed by the user")
    await page.locator("a,button,input,textarea,select,[role=button]").nth(index).fill(value)
    return {"filled": True, "ref": ref, "field": control.get("name") or control.get("placeholder") or control.get("text")}


@mcp.tool()
async def browser_select(ref: str, label_or_value: str) -> dict[str, Any]:
    """Select an option in a visible select control without submitting the form."""
    page = require_page()
    controls = await interactive_snapshot(page)
    index = int(ref)
    if index < 0 or index >= len(controls) or controls[index].get("tag") != "select":
        raise ValueError("Reference is not a select field")
    await page.locator("a,button,input,textarea,select,[role=button]").nth(index).select_option(label=label_or_value)
    return {"selected": True, "ref": ref, "value": label_or_value}


@mcp.tool()
async def browser_back() -> dict[str, Any]:
    """Navigate back one page without submitting a form."""
    page = require_page()
    await page.go_back(wait_until="domcontentloaded", timeout=30000)
    return await page_state(page)


@mcp.tool()
async def browser_close() -> str:
    """Close the remote browser session and clear its page state."""
    await state.close()
    return "Browser session closed"


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": APP_NAME, "mcp_endpoint": "/mcp"})


app = mcp.streamable_http_app()
app.routes.append(Route("/healthz", health, methods=["GET"]))
app.add_middleware(BearerAuthMiddleware)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
