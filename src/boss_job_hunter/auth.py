import json
from pathlib import Path
from playwright.async_api import Browser, BrowserContext

COOKIE_PATH = Path.home() / ".boss_job_hunter" / "cookies.json"
BOSS_URL = "https://www.zhipin.com"
LOGIN_URL = "https://www.zhipin.com/web/user/?ka=header-login"


def save_cookies(cookies: list[dict]) -> None:
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))


def load_cookies() -> list[dict] | None:
    if not COOKIE_PATH.exists():
        return None
    return json.loads(COOKIE_PATH.read_text())


async def login_via_browser(playwright_instance) -> list[dict]:
    """
    Open a headed browser window. User logs in manually (QR code or password).
    Poll until login is detected (redirected away from login page).
    Save and return cookies.
    """
    browser: Browser = await playwright_instance.chromium.launch(headless=False)
    context: BrowserContext = await browser.new_context()
    page = await context.new_page()
    await page.goto(LOGIN_URL)

    print("请在弹出的浏览器窗口中登录 Boss直聘，登录成功后将自动继续...")

    # Poll until URL no longer contains the login path
    for _ in range(120):  # wait up to 120 seconds
        await page.wait_for_timeout(1000)
        if "user" not in page.url and "login" not in page.url:
            break
    else:
        await browser.close()
        raise TimeoutError("登录超时，请重试")

    cookies = await context.cookies()
    await browser.close()
    save_cookies(cookies)
    return cookies


def login_via_cookie_string(cookie_string: str) -> list[dict]:
    """
    Parse a raw cookie string (copied from browser DevTools) into a list of dicts.
    Saves to disk and returns the list.
    """
    cookies = []
    for part in cookie_string.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, value = part.partition("=")
            cookies.append({"name": name.strip(), "value": value.strip(), "domain": ".zhipin.com"})
    save_cookies(cookies)
    return cookies
