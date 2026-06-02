# Boss Job Hunter MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP Server that searches Boss直聘 for jobs, filters by salary/time/HR activity/company size, groups results by company, and exposes two tools (`login`, `search_jobs`) for AI clients.

**Architecture:** Playwright drives a headless Chromium browser authenticated via Cookie. Filter and grouping logic is pure Python with no external dependencies. The MCP layer uses `mcp` (Python SDK) to expose tools over stdio.

**Tech Stack:** Python 3.11+, `mcp` (Python MCP SDK), `playwright`, `pytest`, `pyproject.toml` (uv/pip compatible)

---

## File Map

| File | Responsibility |
|---|---|
| `src/boss_job_hunter/__init__.py` | Package marker |
| `src/boss_job_hunter/models.py` | `Job`, `Company` dataclasses |
| `src/boss_job_hunter/time_parser.py` | Map Boss直聘 time strings → int days |
| `src/boss_job_hunter/salary_parser.py` | Parse "20-30K·13薪" → (min, max) ints |
| `src/boss_job_hunter/filters.py` | Filter and group/sort logic |
| `src/boss_job_hunter/auth.py` | Cookie load/save, browser login flow |
| `src/boss_job_hunter/scraper.py` | Playwright scraping logic |
| `src/boss_job_hunter/rate_limiter.py` | Token-bucket rate limiter (15 req/min) |
| `src/boss_job_hunter/server.py` | MCP Server, tool registration |
| `tests/test_time_parser.py` | Unit tests for time_parser |
| `tests/test_salary_parser.py` | Unit tests for salary_parser |
| `tests/test_filters.py` | Unit tests for filter/group/sort logic |
| `tests/test_auth.py` | Unit tests for cookie save/load |
| `pyproject.toml` | Project metadata, dependencies |
| `README.md` | Setup and usage guide |

---

## Task 1: Project Scaffold

**Files:**
- Create: `src/boss_job_hunter/__init__.py`
- Create: `pyproject.toml`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p src/boss_job_hunter tests
touch src/boss_job_hunter/__init__.py tests/__init__.py
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[project]
name = "boss-job-hunter"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "playwright>=1.44.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/boss_job_hunter"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Install dependencies**

```bash
pip install -e ".[dev]"
playwright install chromium
```

Expected: No errors.

- [ ] **Step 4: Verify pytest runs**

```bash
pytest --collect-only
```

Expected: "no tests ran" (zero errors).

- [ ] **Step 5: Commit**

```bash
git init
git add pyproject.toml src/ tests/
git commit -m "chore: project scaffold"
```

---

## Task 2: Data Models

**Files:**
- Create: `src/boss_job_hunter/models.py`

- [ ] **Step 1: Write models**

```python
# src/boss_job_hunter/models.py
from dataclasses import dataclass, field


@dataclass
class Job:
    title: str
    salary_text: str          # raw text, e.g. "25-40K·13薪"
    salary_min: int           # parsed lower bound in K
    salary_max: int           # parsed upper bound in K
    hr_active_text: str       # raw text, e.g. "3天前活跃"
    hr_active_days: int       # parsed days
    posted_text: str          # raw text, e.g. "2周前发布"
    posted_days: int          # parsed days
    url: str


@dataclass
class Company:
    name: str
    size: str                 # e.g. "10000人以上"
    size_order: int           # numeric for sorting: 0-20→1, 20-99→2, 100-499→3, 500+→4, 10000+→5
    industry: str             # e.g. "互联网"
    funding: str              # e.g. "已上市"
    welfare_tags: list[str] = field(default_factory=list)
    jobs: list[Job] = field(default_factory=list)
```

- [ ] **Step 2: Commit**

```bash
git add src/boss_job_hunter/models.py
git commit -m "feat: add Job and Company data models"
```

---

## Task 3: Time Parser

**Files:**
- Create: `src/boss_job_hunter/time_parser.py`
- Create: `tests/test_time_parser.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_time_parser.py
import pytest
from boss_job_hunter.time_parser import parse_active_days, parse_posted_days


def test_just_active():
    assert parse_active_days("刚刚活跃") == 0

def test_today_active():
    assert parse_active_days("今日活跃") == 1

def test_three_days_active():
    assert parse_active_days("3天前活跃") == 3

def test_this_week_active():
    assert parse_active_days("本周活跃") == 7

def test_two_weeks_active():
    assert parse_active_days("2周前活跃") == 14

def test_one_month_active():
    assert parse_active_days("1个月前活跃") == 30

def test_unknown_active_returns_999():
    assert parse_active_days("很久以前") == 999

def test_posted_days_days():
    assert parse_posted_days("3天前发布") == 3

def test_posted_days_weeks():
    assert parse_posted_days("2周前发布") == 14

def test_posted_days_month():
    assert parse_posted_days("1个月前发布") == 30

def test_posted_days_today():
    assert parse_posted_days("今天发布") == 0

def test_posted_unknown_returns_999():
    assert parse_posted_days("很久以前发布") == 999
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_time_parser.py -v
```

Expected: ImportError or ModuleNotFoundError.

- [ ] **Step 3: Implement time_parser**

```python
# src/boss_job_hunter/time_parser.py
import re

_ACTIVE_MAP = {
    "刚刚活跃": 0,
    "今日活跃": 1,
    "3天前活跃": 3,
    "本周活跃": 7,
    "2周前活跃": 14,
    "1个月前活跃": 30,
}

_POSTED_MAP = {
    "今天发布": 0,
}


def parse_active_days(text: str) -> int:
    """Return days since HR was last active. 999 if unknown."""
    return _ACTIVE_MAP.get(text.strip(), 999)


def parse_posted_days(text: str) -> int:
    """Return days since job was posted. 999 if unknown."""
    text = text.strip()
    if text in _POSTED_MAP:
        return _POSTED_MAP[text]
    m = re.match(r"(\d+)天前", text)
    if m:
        return int(m.group(1))
    m = re.match(r"(\d+)周前", text)
    if m:
        return int(m.group(1)) * 7
    m = re.match(r"(\d+)个月前", text)
    if m:
        return int(m.group(1)) * 30
    return 999
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_time_parser.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/boss_job_hunter/time_parser.py tests/test_time_parser.py
git commit -m "feat: add time string parser"
```

---

## Task 4: Salary Parser

**Files:**
- Create: `src/boss_job_hunter/salary_parser.py`
- Create: `tests/test_salary_parser.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_salary_parser.py
import pytest
from boss_job_hunter.salary_parser import parse_salary


def test_simple_range():
    assert parse_salary("20-30K") == (20, 30)

def test_range_with_bonus():
    assert parse_salary("25-40K·13薪") == (25, 40)

def test_range_with_14_bonus():
    assert parse_salary("15-25K·14薪") == (15, 25)

def test_range_lowercase_k():
    assert parse_salary("20-30k") == (20, 30)

def test_mianyi_returns_none():
    assert parse_salary("面议") is None

def test_empty_returns_none():
    assert parse_salary("") is None

def test_non_standard_returns_none():
    assert parse_salary("薪资待遇优厚") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_salary_parser.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement salary_parser**

```python
# src/boss_job_hunter/salary_parser.py
import re


def parse_salary(text: str) -> tuple[int, int] | None:
    """
    Parse Boss直聘 salary text into (min_k, max_k).
    Returns None for non-standard formats like '面议'.
    """
    if not text:
        return None
    # Match "20-30K" or "20-30K·13薪" (case-insensitive K)
    m = re.match(r"(\d+)-(\d+)[Kk]", text.strip())
    if m:
        return int(m.group(1)), int(m.group(2))
    return None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_salary_parser.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/boss_job_hunter/salary_parser.py tests/test_salary_parser.py
git commit -m "feat: add salary text parser"
```

---

## Task 5: Filter & Group Logic

**Files:**
- Create: `src/boss_job_hunter/filters.py`
- Create: `tests/test_filters.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_filters.py
import pytest
from boss_job_hunter.models import Job, Company
from boss_job_hunter.filters import (
    salary_overlap_ratio,
    filter_job,
    group_and_sort,
)


def make_job(salary_min=20, salary_max=30, hr_days=3, posted_days=10):
    return Job(
        title="工程师", salary_text="20-30K",
        salary_min=salary_min, salary_max=salary_max,
        hr_active_text="3天前活跃", hr_active_days=hr_days,
        posted_text="10天前发布", posted_days=posted_days,
        url="https://example.com",
    )


# --- salary_overlap_ratio ---

def test_exact_match():
    assert salary_overlap_ratio(20, 30, 20, 30) == pytest.approx(1.0)

def test_full_containment_narrow_job():
    # job 25-26 inside target 20-30 → ratio = 1.0 (uses min range as denominator)
    assert salary_overlap_ratio(20, 30, 25, 26) == pytest.approx(1.0)

def test_full_containment_wide_job():
    # job 10-40 contains target 20-30 → ratio = 1.0
    assert salary_overlap_ratio(20, 30, 10, 40) == pytest.approx(1.0)

def test_partial_overlap_50_percent():
    # target 20-30, job 25-35 → intersection=5, min_range=10 → 0.5
    assert salary_overlap_ratio(20, 30, 25, 35) == pytest.approx(0.5)

def test_no_overlap():
    assert salary_overlap_ratio(20, 30, 35, 50) == pytest.approx(0.0)

def test_partial_overlap_15_25_target_20_30():
    # target 20-30 (range 10), job 15-25 (range 10)
    # intersection = 25-20 = 5, min_range = 10 → 0.5
    assert salary_overlap_ratio(20, 30, 15, 25) == pytest.approx(0.5)


# --- filter_job ---

def test_job_passes_all_filters():
    job = make_job(salary_min=20, salary_max=30, hr_days=3, posted_days=10)
    assert filter_job(job, target_min=20, target_max=30, overlap=0.5,
                      posted_within=30, hr_within=7) is True

def test_job_fails_hr_filter():
    job = make_job(hr_days=14)
    assert filter_job(job, target_min=20, target_max=30, overlap=0.5,
                      posted_within=30, hr_within=7) is False

def test_job_fails_posted_filter():
    job = make_job(posted_days=45)
    assert filter_job(job, target_min=20, target_max=30, overlap=0.5,
                      posted_within=30, hr_within=7) is False

def test_job_fails_salary_filter():
    job = make_job(salary_min=35, salary_max=50)
    assert filter_job(job, target_min=20, target_max=30, overlap=0.5,
                      posted_within=30, hr_within=7) is False


# --- group_and_sort ---

def test_same_company_grouped():
    c1 = Company(name="A", size="100-499人", size_order=3,
                 industry="互联网", funding="已上市",
                 jobs=[make_job(), make_job()])
    result = group_and_sort([c1], sort_by="hr_active")
    assert len(result) == 1
    assert len(result[0].jobs) == 2

def test_sort_by_company_size():
    small = Company(name="小", size="0-20人", size_order=1,
                    industry="IT", funding="未融资", jobs=[make_job()])
    big = Company(name="大", size="10000人以上", size_order=5,
                  industry="IT", funding="已上市", jobs=[make_job()])
    result = group_and_sort([small, big], sort_by="company_size")
    assert result[0].name == "大"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_filters.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement filters.py**

```python
# src/boss_job_hunter/filters.py
from boss_job_hunter.models import Job, Company


def salary_overlap_ratio(
    target_min: int, target_max: int,
    job_min: int, job_max: int,
) -> float:
    """
    Overlap ratio = intersection / min(target_range, job_range).
    This ensures a narrow job range fully inside the target scores 1.0,
    and a wide job range containing the target also scores 1.0.
    """
    intersection = max(0, min(target_max, job_max) - max(target_min, job_min))
    denominator = min(target_max - target_min, job_max - job_min)
    if denominator <= 0:
        return 0.0
    return intersection / denominator


def filter_job(
    job: Job,
    target_min: int,
    target_max: int,
    overlap: float,
    posted_within: int,
    hr_within: int,
) -> bool:
    if job.hr_active_days > hr_within:
        return False
    if job.posted_days > posted_within:
        return False
    ratio = salary_overlap_ratio(target_min, target_max, job.salary_min, job.salary_max)
    return ratio >= overlap


_SIZE_ORDER = {
    "0-20人": 1,
    "20-99人": 2,
    "100-499人": 3,
    "500-999人": 4,
    "1000-9999人": 4,
    "10000人以上": 5,
}


def size_order(size: str) -> int:
    return _SIZE_ORDER.get(size, 0)


def group_and_sort(companies: list[Company], sort_by: str) -> list[Company]:
    """Sort company groups. Within each company, sort jobs by hr_active_days asc."""
    for c in companies:
        c.jobs.sort(key=lambda j: j.hr_active_days)

    if sort_by == "company_size":
        companies.sort(key=lambda c: c.size_order, reverse=True)
    elif sort_by == "salary":
        companies.sort(key=lambda c: max((j.salary_max for j in c.jobs), default=0), reverse=True)
    else:  # hr_active (default)
        companies.sort(key=lambda c: min((j.hr_active_days for j in c.jobs), default=999))

    return companies
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_filters.py -v
```

Expected: All passed.

- [ ] **Step 5: Commit**

```bash
git add src/boss_job_hunter/filters.py tests/test_filters.py
git commit -m "feat: add salary filter, grouping and sort logic"
```

---

## Task 6: Rate Limiter

**Files:**
- Create: `src/boss_job_hunter/rate_limiter.py`

- [ ] **Step 1: Implement rate_limiter**

```python
# src/boss_job_hunter/rate_limiter.py
import asyncio
import time


class RateLimiter:
    """
    Token-bucket rate limiter.
    Default: 15 requests per 60 seconds = 4s average interval.
    Excess calls are awaited (not dropped).
    """

    def __init__(self, max_calls: int = 15, period: float = 60.0):
        self._max_calls = max_calls
        self._period = period
        self._min_interval = period / max_calls  # 4.0s
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


_default_limiter = RateLimiter()


async def rate_limited_delay() -> None:
    await _default_limiter.acquire()
```

- [ ] **Step 2: Commit**

```bash
git add src/boss_job_hunter/rate_limiter.py
git commit -m "feat: add token-bucket rate limiter (15 req/min)"
```

---

## Task 7: Auth — Cookie Save/Load

**Files:**
- Create: `src/boss_job_hunter/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth.py
import json
import pytest
from pathlib import Path
from boss_job_hunter.auth import save_cookies, load_cookies, COOKIE_PATH


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("boss_job_hunter.auth.COOKIE_PATH", tmp_path / "cookies.json")
    cookies = [{"name": "token", "value": "abc123", "domain": ".zhipin.com"}]
    save_cookies(cookies)
    loaded = load_cookies()
    assert loaded == cookies


def test_load_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("boss_job_hunter.auth.COOKIE_PATH", tmp_path / "missing.json")
    assert load_cookies() is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_auth.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement auth.py**

```python
# src/boss_job_hunter/auth.py
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
        if "user" not in page.url or "login" not in page.url:
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_auth.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/boss_job_hunter/auth.py tests/test_auth.py
git commit -m "feat: add cookie auth (browser login + manual cookie)"
```

---

## Task 8: Scraper

**Files:**
- Create: `src/boss_job_hunter/scraper.py`

- [ ] **Step 1: Implement scraper.py**

```python
# src/boss_job_hunter/scraper.py
"""
Playwright scraper for Boss直聘 job search.
Returns raw list of (Company, Job) pairs before filtering.
"""
import random
import asyncio
from playwright.async_api import async_playwright, BrowserContext, Page

from boss_job_hunter.auth import load_cookies, BOSS_URL
from boss_job_hunter.models import Job, Company
from boss_job_hunter.time_parser import parse_active_days, parse_posted_days
from boss_job_hunter.salary_parser import parse_salary
from boss_job_hunter.rate_limiter import rate_limited_delay
from boss_job_hunter.filters import size_order

CITY_CODE_MAP = {
    "全国": "100010000",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "武汉": "101200100",
    "西安": "101110100",
    "南京": "101190100",
}


class AuthExpiredError(Exception):
    pass


class CaptchaError(Exception):
    pass


async def _check_page_valid(page: Page) -> None:
    url = page.url
    if "login" in url or "user/?ka" in url:
        raise AuthExpiredError("Cookie 已失效，请重新运行 login 工具")
    if await page.query_selector(".captcha") or await page.query_selector("#captcha-box"):
        raise CaptchaError("检测到验证码，请稍后重试或重新登录")


async def scrape_jobs(
    keyword: str,
    city: str,
    max_pages: int = 5,
) -> tuple[list[tuple[Company, Job]], list[tuple[Company, str]]]:
    """
    Scrape Boss直聘 search results.

    Returns:
        (parsed_pairs, mianyi_pairs)
        parsed_pairs: list of (Company, Job) with salary parsed
        mianyi_pairs: list of (Company, raw_salary_text) for non-standard salary
    """
    city_code = CITY_CODE_MAP.get(city, "100010000")
    cookies = load_cookies()
    if not cookies:
        raise AuthExpiredError("未找到登录信息，请先运行 login 工具")

    parsed_pairs: list[tuple[Company, Job]] = []
    mianyi_pairs: list[tuple[Company, str]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context()
        await context.add_cookies(cookies)

        for page_num in range(1, max_pages + 1):
            await rate_limited_delay()
            url = (
                f"{BOSS_URL}/web/geek/job?"
                f"query={keyword}&city={city_code}&page={page_num}"
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle")
            await _check_page_valid(page)

            job_cards = await page.query_selector_all(".job-card-wrapper")
            if not job_cards:
                break

            for card in job_cards:
                try:
                    company, job_or_salary = await _parse_card(card)
                    if isinstance(job_or_salary, Job):
                        parsed_pairs.append((company, job_or_salary))
                    else:
                        mianyi_pairs.append((company, job_or_salary))
                except Exception:
                    continue  # skip malformed cards

            await page.close()
            # Random delay between pages
            await asyncio.sleep(random.uniform(1.0, 3.0))

        await browser.close()

    return parsed_pairs, mianyi_pairs


async def _parse_card(card) -> tuple[Company, Job | str]:
    """Parse a single job card. Returns (Company, Job) or (Company, salary_text) for 面议."""

    title = await _text(card, ".job-name")
    salary_text = await _text(card, ".salary")
    hr_active_text = await _text(card, ".boss-active-time")
    posted_text = await _text(card, ".job-limit .publish-time", default="今天发布")
    href = await _attr(card, "a.job-card-left", "href")
    url = f"https://www.zhipin.com{href}" if href else ""

    company_name = await _text(card, ".company-name")
    size_text = await _text(card, ".company-tag-list li:nth-child(2)", default="")
    industry_text = await _text(card, ".company-tag-list li:nth-child(1)", default="")
    funding_text = await _text(card, ".company-tag-list li:nth-child(3)", default="")
    welfare_els = await card.query_selector_all(".tag-list li")
    welfare_tags = [await el.inner_text() for el in welfare_els]

    company = Company(
        name=company_name,
        size=size_text,
        size_order=size_order(size_text),
        industry=industry_text,
        funding=funding_text,
        welfare_tags=welfare_tags,
    )

    salary_parsed = parse_salary(salary_text)
    if salary_parsed is None:
        return company, salary_text  # 面议 or non-standard

    salary_min, salary_max = salary_parsed
    job = Job(
        title=title,
        salary_text=salary_text,
        salary_min=salary_min,
        salary_max=salary_max,
        hr_active_text=hr_active_text,
        hr_active_days=parse_active_days(hr_active_text),
        posted_text=posted_text,
        posted_days=parse_posted_days(posted_text),
        url=url,
    )
    return company, job


async def _text(el, selector: str, default: str = "") -> str:
    node = await el.query_selector(selector)
    if node is None:
        return default
    return (await node.inner_text()).strip()


async def _attr(el, selector: str, attr: str) -> str:
    node = await el.query_selector(selector)
    if node is None:
        return ""
    return (await node.get_attribute(attr)) or ""
```

- [ ] **Step 2: Commit**

```bash
git add src/boss_job_hunter/scraper.py
git commit -m "feat: add Playwright scraper for Boss直聘"
```

---

## Task 9: MCP Server

**Files:**
- Create: `src/boss_job_hunter/server.py`

- [ ] **Step 1: Implement server.py**

```python
# src/boss_job_hunter/server.py
import asyncio
import json
from dataclasses import asdict

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from boss_job_hunter.auth import (
    login_via_browser,
    login_via_cookie_string,
    load_cookies,
)
from boss_job_hunter.scraper import scrape_jobs, AuthExpiredError, CaptchaError
from boss_job_hunter.filters import filter_job, group_and_sort, size_order
from boss_job_hunter.models import Company

app = Server("boss-job-hunter")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="login",
            description="登录 Boss直聘。method='browser' 打开本地浏览器手动登录并自动保存 Cookie；method='cookie' 粘贴 Cookie 字符串。",
            inputSchema={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["browser", "cookie"],
                        "description": "登录方式",
                    },
                    "cookie_string": {
                        "type": "string",
                        "description": "当 method=cookie 时提供，从浏览器 DevTools 复制的 Cookie 字符串",
                    },
                },
                "required": ["method"],
            },
        ),
        types.Tool(
            name="search_jobs",
            description="在 Boss直聘 搜索职位，按薪资/HR活跃时间/公司规模过滤，按公司分组返回结果。",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "职位关键词，如 Java工程师"},
                    "city": {"type": "string", "description": "城市，如 上海"},
                    "salary_min": {"type": "integer", "description": "目标薪资下限（K）"},
                    "salary_max": {"type": "integer", "description": "目标薪资上限（K）"},
                    "salary_overlap": {
                        "type": "number",
                        "default": 0.5,
                        "description": "薪资交集比例阈值，默认 0.5",
                    },
                    "posted_within_days": {
                        "type": "integer",
                        "default": 30,
                        "description": "发布时间限制（天），默认 30",
                    },
                    "hr_active_within_days": {
                        "type": "integer",
                        "default": 7,
                        "description": "HR 活跃时间限制（天），默认 7",
                    },
                    "company_size": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "公司规模过滤，如 ['100-499人','500-999人']",
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["hr_active", "salary", "company_size"],
                        "default": "hr_active",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 50,
                        "description": "最多返回职位数",
                    },
                },
                "required": ["keyword", "city", "salary_min", "salary_max"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "login":
        return await _handle_login(arguments)
    elif name == "search_jobs":
        return await _handle_search(arguments)
    raise ValueError(f"Unknown tool: {name}")


async def _handle_login(args: dict) -> list[types.TextContent]:
    method = args["method"]
    try:
        if method == "browser":
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                await login_via_browser(p)
            return [types.TextContent(type="text", text="登录成功！Cookie 已保存，可以开始搜索职位了。")]
        elif method == "cookie":
            cookie_string = args.get("cookie_string", "")
            if not cookie_string:
                return [types.TextContent(type="text", text="错误：method=cookie 时必须提供 cookie_string 参数")]
            login_via_cookie_string(cookie_string)
            return [types.TextContent(type="text", text="Cookie 已保存，可以开始搜索职位了。")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"登录失败：{e}")]


async def _handle_search(args: dict) -> list[types.TextContent]:
    keyword = args["keyword"]
    city = args["city"]
    salary_min = args["salary_min"]
    salary_max = args["salary_max"]
    salary_overlap = args.get("salary_overlap", 0.5)
    posted_within = args.get("posted_within_days", 30)
    hr_within = args.get("hr_active_within_days", 7)
    company_size_filter: list[str] | None = args.get("company_size")
    sort_by = args.get("sort_by", "hr_active")
    max_results = args.get("max_results", 50)

    try:
        parsed_pairs, mianyi_pairs = await scrape_jobs(keyword, city)
    except AuthExpiredError as e:
        return [types.TextContent(type="text", text=str(e))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"搜索出错：{e}")]

    # Filter and group
    company_map: dict[str, Company] = {}
    total = 0

    for company, job in parsed_pairs:
        if total >= max_results:
            break
        if company_size_filter and company.size not in company_size_filter:
            continue
        if not filter_job(job, salary_min, salary_max, salary_overlap, posted_within, hr_within):
            continue
        if company.name not in company_map:
            company_map[company.name] = Company(
                name=company.name, size=company.size,
                size_order=company.size_order, industry=company.industry,
                funding=company.funding, welfare_tags=company.welfare_tags,
            )
        company_map[company.name].jobs.append(job)
        total += 1

    companies = list(company_map.values())
    companies = group_and_sort(companies, sort_by)

    # Handle 面议 group
    mianyi_company = None
    if mianyi_pairs:
        mianyi_company = {"company": "薪资面议", "size": "-", "industry": "-",
                          "funding": "-", "welfare_tags": [],
                          "jobs": [{"title": c.name, "salary": s, "hr_active": "-",
                                    "posted": "-", "url": ""} for c, s in mianyi_pairs]}

    if not companies and not mianyi_company:
        suggestion = (
            f"未找到符合条件的职位。当前过滤条件：\n"
            f"  关键词={keyword}，城市={city}\n"
            f"  薪资={salary_min}-{salary_max}K（交集≥{salary_overlap*100:.0f}%）\n"
            f"  发布时间≤{posted_within}天，HR活跃≤{hr_within}天\n\n"
            f"建议：降低 salary_overlap，或放宽 hr_active_within_days。"
        )
        return [types.TextContent(type="text", text=suggestion)]

    result = [asdict(c) for c in companies]
    if mianyi_company:
        result.append(mianyi_company)

    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


def main():
    asyncio.run(stdio_server(app))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add entry point to pyproject.toml**

Add under `[project]` section:

```toml
[project.scripts]
boss-job-hunter = "boss_job_hunter.server:main"
```

- [ ] **Step 3: Reinstall to register entry point**

```bash
pip install -e ".[dev]"
```

- [ ] **Step 4: Commit**

```bash
git add src/boss_job_hunter/server.py pyproject.toml
git commit -m "feat: add MCP server with login and search_jobs tools"
```

---

## Task 10: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md**

```markdown
# Boss Job Hunter 🎯

通过 AI 对话在 Boss直聘 找工作的 MCP Server。支持薪资、HR活跃时间、公司规模等多维度筛选，结果按公司分组展示。

## 环境要求

- Python 3.11+
- pip 或 uv

## 安装

```bash
git clone https://github.com/<your-username>/boss-job-hunter
cd boss-job-hunter
pip install -e .
playwright install chromium
```

## 配置到 Claude Code

编辑 `~/.claude/claude_desktop_config.json`（或你的 AI 客户端 MCP 配置文件）：

```json
{
  "mcpServers": {
    "boss-job-hunter": {
      "command": "python",
      "args": ["-m", "boss_job_hunter.server"]
    }
  }
}
```

## 使用

**第一步：登录**

> 帮我登录 Boss直聘（打开浏览器扫码）

或者提供 Cookie 字符串：

> 用这个 Cookie 登录：`token=xxx; ...`

**第二步：搜索**

> 帮我在上海找 Java 工程师，薪资 20-30K

> 帮我在北京找产品经理，薪资 15-25K，只看 100 人以上的公司，按公司规模排序

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| keyword | 必填 | 职位关键词 |
| city | 必填 | 城市名 |
| salary_min / salary_max | 必填 | 目标薪资范围（K） |
| salary_overlap | 0.5 | 薪资交集比例，0.5 = 50% |
| posted_within_days | 30 | 职位发布时间限制 |
| hr_active_within_days | 7 | HR 活跃时间限制 |
| company_size | 不限 | 如 ["100-499人", "500-999人"] |
| sort_by | hr_active | hr_active / salary / company_size |
| max_results | 50 | 最多返回职位数 |
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and usage guide"
```

---

## Task 11: Full Run Test

- [ ] **Step 1: Run all unit tests**

```bash
pytest -v
```

Expected: All tests pass.

- [ ] **Step 2: Smoke test MCP server starts**

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python -m boss_job_hunter.server
```

Expected: JSON response listing `login` and `search_jobs` tools.

- [ ] **Step 3: Tag initial release**

```bash
git tag v0.1.0
```
```
