import json
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from playwright.async_api import Browser, BrowserContext

COOKIE_PATH = Path.home() / ".boss_job_hunter" / "cookies.json"
BOSS_URL = "https://www.zhipin.com"
LOGIN_URL = "https://www.zhipin.com/web/user/?ka=header-login"

CHROME_COOKIE_DB = (
    Path.home()
    / "AppData" / "Local" / "Google" / "Chrome"
    / "User Data" / "Default" / "Network" / "Cookies"
)
# Fallback for older Chrome versions
CHROME_COOKIE_DB_FALLBACK = (
    Path.home()
    / "AppData" / "Local" / "Google" / "Chrome"
    / "User Data" / "Default" / "Cookies"
)


def save_cookies(cookies: list[dict]) -> None:
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))


def load_cookies() -> list[dict] | None:
    if not COOKIE_PATH.exists():
        return None
    return json.loads(COOKIE_PATH.read_text())


def read_chrome_cookies() -> list[dict]:
    """
    Read Boss直聘 cookies directly from Chrome's SQLite database.
    Chrome must be closed before calling this (database is locked while Chrome runs).
    Note: cookie values may be encrypted (Chrome 80+), returns raw encrypted bytes as placeholder.
    """
    db_path = CHROME_COOKIE_DB if CHROME_COOKIE_DB.exists() else CHROME_COOKIE_DB_FALLBACK
    if not db_path.exists():
        raise FileNotFoundError(f"找不到 Chrome Cookie 数据库：{db_path}")

    # Copy to temp file to avoid lock issues
    tmp = Path(tempfile.mktemp(suffix=".db"))
    shutil.copy2(db_path, tmp)

    try:
        conn = sqlite3.connect(tmp)
        cursor = conn.execute(
            "SELECT name, value, encrypted_value, host_key, path, "
            "expires_utc, is_secure, is_httponly, samesite "
            "FROM cookies WHERE host_key LIKE '%zhipin.com%'"
        )
        rows = cursor.fetchall()
        conn.close()
    finally:
        tmp.unlink(missing_ok=True)

    # Pre-load AES key once for efficiency
    try:
        aes_key = _get_chrome_encryption_key()
    except Exception:
        aes_key = None

    cookies = []
    for name, value, encrypted_value, host, path, expires, secure, httponly, samesite in rows:
        actual_value = value
        if not value and encrypted_value:
            actual_value = _decrypt_chrome_cookie(encrypted_value, aes_key)
        if actual_value is None:
            continue
        cookies.append({
            "name": name,
            "value": actual_value,
            "domain": host,
            "path": path,
            "secure": bool(secure),
            "httpOnly": bool(httponly),
        })

    auth_keys = {"wt2", "bst", "__zp_stoken__"}
    found = {c["name"] for c in cookies}
    if not auth_keys.intersection(found):
        raise RuntimeError(
            "Cookie 解密失败，无法读取登录信息。\n"
            "请改用 cookie 方式登录：\n"
            "1. 用 Chrome 打开 https://www.zhipin.com 并登录\n"
            "2. 按 F12 → Network → 刷新页面 → 点任意请求\n"
            "3. 在 Request Headers 找到 Cookie 行，复制整行值\n"
            "4. 告诉我：用这个 Cookie 登录：<粘贴>"
        )

    return cookies


def _get_chrome_encryption_key() -> bytes:
    """Get Chrome's AES key from Local State (decrypted via DPAPI)."""
    import base64
    import win32crypt  # type: ignore

    local_state_path = (
        Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Local State"
    )
    local_state = json.loads(local_state_path.read_text(encoding="utf-8"))
    encrypted_key_b64 = local_state["os_crypt"]["encrypted_key"]
    encrypted_key = base64.b64decode(encrypted_key_b64)[5:]  # strip "DPAPI" prefix
    return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]


def _decrypt_chrome_cookie(encrypted_value: bytes, key: bytes | None = None) -> str | None:
    """Decrypt Chrome cookie value. Tries AES-GCM (v10/v20) first, then DPAPI."""
    from Crypto.Cipher import AES  # type: ignore

    # Chrome 80+: starts with b"v10" or b"v20"
    if encrypted_value[:3] in (b"v10", b"v20"):
        try:
            if key is None:
                key = _get_chrome_encryption_key()
            iv = encrypted_value[3:15]
            ciphertext = encrypted_value[15:-16]
            tag = encrypted_value[-16:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
            return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
        except Exception:
            return None

    # Older Chrome: DPAPI encrypted
    try:
        import win32crypt  # type: ignore
        return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode("utf-8")
    except Exception:
        return None


async def login_via_browser(playwright_instance) -> list[dict]:
    """
    Open Boss直聘 login page in Chrome with remote debugging enabled.
    After login, read cookies via CDP (no DevTools UI, undetectable).
    """
    import asyncio

    # Kill any existing Chrome with debug port
    subprocess.run(
        ["taskkill", "/F", "/IM", "chrome.exe"],
        capture_output=True,
    )
    await asyncio.sleep(1)

    subprocess.Popen(
        [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "--remote-debugging-port=9222",
            "--user-data-dir=C:\\Temp\\chrome-debug-profile",
            "--no-first-run",
            "--no-default-browser-check",
            LOGIN_URL,
        ],
        creationflags=0x00000008,
    )
    raise RuntimeError(
        "已用你的 Chrome 打开 Boss直聘 登录页（已开启远程调试）。\n\n"
        "请按以下步骤操作：\n"
        "1. 在浏览器中正常登录（扫码或账号密码均可）\n"
        "2. 登录成功后告诉我：读取 Cookie\n"
        "（不需要关闭浏览器，不需要打开 DevTools）"
    )


async def login_from_chrome_db(playwright_instance) -> list[dict]:
    """Read cookies from Chrome via CDP remote debugging port."""
    import urllib.request

    # Connect via Playwright to existing Chrome debug session
    browser = await playwright_instance.chromium.connect_over_cdp("http://localhost:9222")
    contexts = browser.contexts
    if not contexts:
        raise RuntimeError("无法连接到 Chrome，请确认已通过 '登录 Boss直聘' 打开浏览器")

    context = contexts[0]
    cookies = await context.cookies("https://www.zhipin.com")
    await browser.close()

    auth_keys = {"wt2", "bst", "__zp_stoken__"}
    found = {c["name"] for c in cookies}
    if not auth_keys.intersection(found):
        raise RuntimeError(
            "未检测到 Boss直聘 登录状态，请确认已在浏览器中完成登录后重试"
        )

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
