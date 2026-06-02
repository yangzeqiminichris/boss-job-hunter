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
