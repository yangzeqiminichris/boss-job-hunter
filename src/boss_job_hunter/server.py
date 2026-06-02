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


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()
