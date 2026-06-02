# Boss Job Hunter MCP Server — Design Spec

Date: 2026-06-02

## Overview

A Python MCP Server that searches Boss直聘 for jobs matching user-defined criteria. Distributed as a GitHub repo; users clone and add it to their AI client (Claude Code, Cursor, etc.) to search jobs via natural language.

---

## Architecture

```
boss-job-hunter/
├── src/
│   └── boss_job_hunter/
│       ├── server.py        # MCP Server entry point, tool registration
│       ├── scraper.py       # Playwright browser automation
│       ├── filters.py       # Salary / time / company-size filter logic
│       └── models.py        # Job and Company data models
├── pyproject.toml
└── README.md
```

### Data Flow

1. Claude calls MCP tool `search_jobs` with keyword, city, salary range, filters
2. `scraper.py` launches Playwright (headless), authenticates via saved Cookie
3. Scrapes job listing pages, extracts: title, company, salary, posted date, HR active time, URL
4. `filters.py` applies: posted < N days + HR active < M days + salary overlap >= threshold + company size
5. Groups results by company, sorts groups and jobs within groups
6. Returns structured JSON to Claude

---

## MCP Tools

### `login`

Handles authentication. Saves Cookie to `~/.boss_job_hunter/cookies.json` for reuse.

| Parameter | Type | Description |
|---|---|---|
| `method` | `"qrcode" \| "cookie"` | Login method |
| `cookie_string` | `string?` | Required when method is `"cookie"` |

- **browser**: Opens a local headed Chromium window pointing to Boss直聘 login page. User logs in however they prefer (QR code, username/password, etc.). Server polls until login is detected, then saves Cookie automatically and closes the browser. Works with any AI client — no QR rendering required.
- **cookie**: User pastes cookie string from browser DevTools; parsed and saved.

### `search_jobs`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `keyword` | `string` | required | Job title keyword, e.g. "Java工程师" |
| `city` | `string` | required | City name, e.g. "上海" |
| `salary_min` | `int` | required | Target salary lower bound (K/month) |
| `salary_max` | `int` | required | Target salary upper bound (K/month) |
| `salary_overlap` | `float` | `0.5` | Minimum overlap ratio vs target range |
| `posted_within_days` | `int` | `30` | Max days since job was posted |
| `hr_active_within_days` | `int` | `7` | Max days since HR was last active |
| `company_size` | `list[str]?` | none | Filter by size buckets: "0-20人", "20-99人", "100-499人", "500人以上" |
| `sort_by` | `string` | `"hr_active"` | Sort field: `"hr_active"`, `"salary"`, `"company_size"` |
| `max_results` | `int` | `50` | Max jobs to return |

**Return format:** List of company groups, each containing company info and its matching jobs.

```json
[
  {
    "company": "字节跳动",
    "size": "10000人以上",
    "industry": "互联网",
    "funding": "已上市",
    "welfare_tags": ["年终奖", "弹性工作", "五险一金"],
    "jobs": [
      {
        "title": "Java工程师",
        "salary": "25-40K",
        "hr_active": "3天前活跃",
        "posted": "2周前",
        "url": "https://www.zhipin.com/..."
      }
    ]
  }
]
```

---

## Salary Filter Logic

```
intersection = max(0, min(target_max, job_max) - max(target_min, job_min))
overlap_ratio = intersection / min(target_max - target_min, job_max - job_min)
passes = overlap_ratio >= salary_overlap
```

Using `min(target_range, job_range)` as the denominator ensures narrow job ranges fully contained within the target range are never incorrectly filtered (e.g. job=25-26K, target=20-30K → ratio=1.0).

Jobs with non-standard salary (e.g. "面议") bypass the filter and are returned in a separate group at the end of results.

---

## Error Handling

| Situation | Behavior |
|---|---|
| Cookie expired | Return error: "Cookie 已失效，请重新运行 login 工具" |
| CAPTCHA / redirect to login | Stop scraping, prompt user to retry or re-login |
| Zero results after filtering | Return filter summary + suggestion to relax constraints |
| Non-standard salary format | Collect in "面议" group, append to results |

Anti-scraping: random 1–3s delay between page requests. Global rate limit: max 15 requests per minute (4s minimum interval on average); excess requests are queued and delayed automatically.

---

## HR Activity & Posted Time Text Mapping

Boss直聘 displays activity and posted time as enum strings, not exact timestamps. These are mapped to integer days for filtering:

| Display Text | Days Value |
|---|---|
| 刚刚活跃 | 0 |
| 今日活跃 | 1 |
| 3天前活跃 | 3 |
| 本周活跃 | 7 |
| 2周前活跃 | 14 |
| 1个月前活跃 | 30 |

`hr_active_within_days=7` passes: 刚刚活跃, 今日活跃, 3天前活跃, 本周活跃.

Posted time uses the same mapping pattern (e.g. "3天前发布" → 3, "2周前发布" → 14).

---

## Setup (for end users)

```bash
git clone https://github.com/<user>/boss-job-hunter
cd boss-job-hunter
pip install -e ".[dev]"
playwright install chromium
```

Add to Claude Code MCP config:
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

Then in Claude: "帮我在上海找 Java 工程师，薪资 20-30K"
