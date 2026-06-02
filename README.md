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

> **国内用户提示：** `playwright install chromium` 需要从 Google 服务器下载，请开启代理后再执行。或使用镜像：
> ```bash
> PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright playwright install chromium
> ```

## 配置到 Claude Code

编辑 `~/.claude/claude_desktop_config.json`（或你的 AI 客户端 MCP 配置文件）：

```json
{
  "mcpServers": {
    "boss-job-hunter": {
      "command": "python",
      "args": ["-m", "boss_job_hunter.server"],
      "cwd": "/path/to/boss-job-hunter"
    }
  }
}
```

> **提示：** 如果 `python` 不在 PATH，请使用完整路径，例如 `C:\Users\yourname\miniconda3\python.exe`

## 使用

**第一步：登录（首次使用）**

在 Claude 中说：
> 帮我登录 Boss直聘

Claude 会打开一个浏览器窗口，在里面正常登录（扫码或账号密码均可），登录成功后浏览器自动关闭，Cookie 保存到本地。

或者，如果你知道如何从浏览器 DevTools 获取 Cookie：
> 用这个 Cookie 登录：`token=xxx; wt2=yyy; ...`

**第二步：搜索职位**

> 帮我在上海找 Java 工程师，薪资 20-30K

> 帮我在北京找产品经理，薪资 15-25K，只看 100 人以上的公司，按公司规模排序

> 在深圳搜 Python 后端，薪资 25-40K，HR 必须是本周活跃的

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| keyword | 必填 | 职位关键词 |
| city | 必填 | 城市名（北京/上海/广州/深圳/杭州/成都/武汉/西安/南京） |
| salary_min / salary_max | 必填 | 目标薪资范围（K/月） |
| salary_overlap | 0.5 | 薪资交集比例阈值，0.5 = 50%。调低可匹配更多职位 |
| posted_within_days | 30 | 职位发布时间限制（天） |
| hr_active_within_days | 7 | HR 最近活跃时间限制（天）。7 = 本周内活跃 |
| company_size | 不限 | 公司规模过滤，如 `["100-499人", "500-999人"]` |
| sort_by | hr_active | 排序方式：`hr_active`（最近活跃）/ `salary`（薪资）/ `company_size`（规模） |
| max_results | 50 | 最多返回职位数 |

## 薪资匹配说明

使用交集比例而非精确匹配，更灵活：

- 目标 20-30K，职位 25-26K → 交集 100%（职位完全在范围内）✅
- 目标 20-30K，职位 10-40K → 交集 100%（范围完全被包含）✅  
- 目标 20-30K，职位 15-25K → 交集 50%（满足默认阈值）✅
- 目标 20-30K，职位 35-50K → 交集 0%，过滤掉 ❌

`salary_overlap` 设为 `0` 可关闭薪资过滤。

## 返回格式

结果按公司分组，JSON 格式：

```json
[
  {
    "name": "字节跳动",
    "size": "10000人以上",
    "industry": "互联网",
    "funding": "已上市",
    "welfare_tags": ["年终奖", "弹性工作", "五险一金"],
    "jobs": [
      {
        "title": "Java工程师",
        "salary_text": "25-40K·13薪",
        "hr_active_text": "3天前活跃",
        "posted_text": "2周前发布",
        "url": "https://www.zhipin.com/..."
      }
    ]
  }
]
```

## 常见问题

**Q: 搜索提示 "Cookie 已失效"**  
A: 重新运行登录流程即可。

**Q: 搜索没有结果**  
A: 尝试降低 `salary_overlap`（如设为 0.3），或放宽 `hr_active_within_days`（如设为 14）。

**Q: 找不到某个城市**  
A: 目前支持：北京、上海、广州、深圳、杭州、成都、武汉、西安、南京。其他城市默认搜索全国。
