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
    login_from_chrome_db,
    COOKIE_PATH,
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
                        "enum": ["browser", "chrome_db", "cookie"],
                        "description": "登录方式：browser=打开Chrome登录页（需关闭Chrome后用chrome_db读取）；chrome_db=从本机Chrome数据库读取Cookie（登录后关闭Chrome再用）；cookie=直接粘贴Cookie字符串",
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
            name="read_current_page",
            description="读取当前 Chrome 页面上的职位列表并按条件过滤。在用户手动搜索并看到结果后调用。",
            inputSchema={
                "type": "object",
                "properties": {
                    "salary_min": {"type": "integer", "description": "目标薪资下限（K）"},
                    "salary_max": {"type": "integer", "description": "目标薪资上限（K）"},
                    "salary_overlap": {"type": "number", "default": 0.5},
                    "posted_within_days": {"type": "integer", "default": 30},
                    "hr_active_within_days": {"type": "integer", "default": 7},
                    "company_size": {"type": "array", "items": {"type": "string"}},
                    "sort_by": {"type": "string", "enum": ["hr_active", "salary", "company_size"], "default": "hr_active"},
                },
                "required": ["salary_min", "salary_max"],
            },
        ),
        types.Tool(
            name="logout",
            description="清除本地保存的 Boss直聘 Cookie，退出登录状态。",
            inputSchema={"type": "object", "properties": {}},
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
    elif name == "logout":
        return _handle_logout()
    elif name == "open_search":
        return await _handle_open_search(arguments)
    elif name == "read_current_page":
        return await _handle_read_current_page(arguments)
    elif name == "search_jobs":
        return await _handle_search(arguments)
    raise ValueError(f"Unknown tool: {name}")


async def _handle_login(args: dict) -> list[types.TextContent]:
    method = args["method"]
    try:
        if method == "browser":
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                try:
                    await login_via_browser(p)
                except RuntimeError as e:
                    return [types.TextContent(type="text", text=str(e))]
            return [types.TextContent(type="text", text="登录成功！Cookie 已保存，可以开始搜索职位了。")]
        elif method == "chrome_db":
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                try:
                    await login_from_chrome_db(p)
                    return [types.TextContent(type="text", text="已通过 Chrome 远程调试读取 Cookie，登录成功！可以开始搜索了。")]
                except Exception as e:
                    return [types.TextContent(type="text", text=f"读取失败：{e}")]
        elif method == "cookie":
            cookie_string = args.get("cookie_string", "")
            if not cookie_string:
                return [types.TextContent(type="text", text="错误：method=cookie 时必须提供 cookie_string 参数")]
            login_via_cookie_string(cookie_string)
            return [types.TextContent(type="text", text="Cookie 已保存，可以开始搜索职位了。")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"登录失败：{e}")]


async def _handle_open_search(args: dict) -> list[types.TextContent]:
    from urllib.parse import quote
    from boss_job_hunter.scraper import CITY_CODE_MAP
    keyword = args["keyword"]
    city = args.get("city", "全国")
    city_code = CITY_CODE_MAP.get(city, "100010000")
    url = f"https://www.zhipin.com/web/geek/job?query={quote(keyword)}&city={city_code}"
    return [types.TextContent(type="text", text=(
        f"请在已打开的 Chrome 窗口中访问：\n{url}\n\n"
        f"等搜索结果加载完毕后，告诉我"读取当前页面"。"
    ))]


async def _handle_read_current_page(args: dict) -> list[types.TextContent]:
    from playwright.async_api import async_playwright
    from boss_job_hunter.scraper import _parse_card
    salary_min = args["salary_min"]
    salary_max = args["salary_max"]
    salary_overlap = args.get("salary_overlap", 0.5)
    posted_within = args.get("posted_within_days", 30)
    hr_within = args.get("hr_active_within_days", 7)
    company_size_filter = args.get("company_size")
    sort_by = args.get("sort_by", "hr_active")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            ctx = browser.contexts[0]
            # Find the Boss直聘 job search page
            page = None
            for pg in ctx.pages:
                if "zhipin.com" in pg.url:
                    page = pg
                    break
            if page is None:
                return [types.TextContent(type="text", text="未找到 Boss直聘 页面，请先在 Chrome 中打开搜索结果页。")]

            job_cards = await page.query_selector_all(".job-card-wrapper")
            if not job_cards:
                return [types.TextContent(type="text", text=f"当前页面（{page.url[:80]}）未找到职位卡片，请确认已在搜索结果页。")]

            from boss_job_hunter.models import Company
            parsed_pairs, mianyi_pairs = [], []
            for card in job_cards:
                try:
                    company, job_or_salary = await _parse_card(card)
                    if isinstance(job_or_salary, str):
                        mianyi_pairs.append((company, job_or_salary))
                    else:
                        parsed_pairs.append((company, job_or_salary))
                except Exception:
                    continue

    except Exception as e:
        return [types.TextContent(type="text", text=f"读取页面失败：{e}")]

    company_map: dict[str, Company] = {}
    for company, job in parsed_pairs:
        if company_size_filter and company.size not in company_size_filter:
            continue
        if not filter_job(job, salary_min, salary_max, salary_overlap, posted_within, hr_within):
            continue
        if company.name not in company_map:
            company_map[company.name] = Company(
                name=company.name, size=company.size, size_order=company.size_order,
                industry=company.industry, funding=company.funding, welfare_tags=company.welfare_tags,
            )
        company_map[company.name].jobs.append(job)

    companies = list(company_map.values())
    companies = group_and_sort(companies, sort_by)

    if not companies:
        return [types.TextContent(type="text", text=f"当前页面共 {len(job_cards)} 个职位，过滤后无符合条件的结果。\n建议放宽薪资或活跃时间条件。")]

    result = [asdict(c) for c in companies]
    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


def _handle_logout() -> list[types.TextContent]:
    if COOKIE_PATH.exists():
        COOKIE_PATH.unlink()
        return [types.TextContent(type="text", text="Cookie 已清除，已退出登录。")]
    return [types.TextContent(type="text", text="本地没有保存的 Cookie，无需清除。")]


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
    except CaptchaError as e:
        return [types.TextContent(type="text", text=f"检测到验证码，请稍后重试或重新登录。详情：{e}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"搜索出错：{e}")]

    # Filter all pairs first, then cap
    company_map: dict[str, Company] = {}

    for company, job in parsed_pairs:
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

    companies = list(company_map.values())
    companies = group_and_sort(companies, sort_by)

    # Cap after sorting so max_results applies to the best results
    total = 0
    capped_companies = []
    for c in companies:
        if total >= max_results:
            break
        capped_companies.append(c)
        total += len(c.jobs)
    companies = capped_companies

    # Handle 面议 group — also filter by company_size if specified
    mianyi_company = None
    filtered_mianyi = [
        (c, s) for c, s in mianyi_pairs
        if not company_size_filter or c.size in company_size_filter
    ]
    if filtered_mianyi:
        mianyi_company = {"company": "薪资面议", "size": "-", "industry": "-",
                          "funding": "-", "welfare_tags": [],
                          "jobs": [{"title": c.name, "salary": s, "hr_active": "-",
                                    "posted": "-", "url": ""} for c, s in filtered_mianyi]}

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


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()
