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

使用 `claude mcp add` 命令一行完成配置（推荐）：

**macOS / Linux：**
```bash
claude mcp add boss-job-hunter -s user -- python -m boss_job_hunter.server
```

**Windows（使用 conda/miniconda）：**
```powershell
claude mcp add boss-job-hunter -s user -- C:\Users\yourname\miniconda3\python.exe -m boss_job_hunter.server
```

> **说明：**
> - `-s user` 表示写入用户级配置（`~/.claude.json`），对所有项目生效
> - `--` 后面是完整的启动命令，避免 `-m` 被 claude 误解析
> - 如果 `python` 不在 PATH（Windows 常见），请使用 Python 完整路径

配置完成后重启 Claude Code，输入 `/mcp` 确认 `boss-job-hunter` 状态为 Connected。

> **注意：** MCP 配置写入 `~/.claude.json`，不是 `~/.claude/settings.json`。两个文件用途不同，请勿混淆。

## 使用

**第一步：登录（首次使用）**

在 Claude 中说：
> 帮我登录 Boss直聘

Claude 会以远程调试模式打开一个独立的 Chrome 窗口，在里面正常登录（扫码或账号密码均可）。

登录成功后说：
> 读取 Cookie

Claude 会通过 Chrome 远程调试协议（CDP）静默读取 Cookie 并保存，**不需要打开 DevTools，不会被 Boss直聘 检测到**。

> **说明：** Chrome 会使用独立的临时 Profile（`C:\Temp\chrome-debug-profile`），与你日常使用的 Chrome 互不干扰。每次登录都需要重新扫码/输入密码。

如需重新登录，先清除 Cookie：
> 帮我退出登录

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

## 安装 Skill（可选，推荐）

安装 Skill 后，你可以直接对 Claude 说"帮我找工作"，不需要手动指定参数格式。

**Windows：**
```powershell
# 找到 superpowers 插件目录（版本号可能不同）
$superpowers = Get-ChildItem "$env:USERPROFILE\.claude\plugins\cache\claude-plugins-official\superpowers" | Sort-Object Name -Descending | Select-Object -First 1 -ExpandProperty FullName
$dest = "$superpowers\skills\boss-job-hunter"
New-Item -ItemType Directory -Force $dest
Copy-Item "skill\SKILL.md" $dest
```

**macOS / Linux：**
```bash
# 找到 superpowers 插件目录（版本号可能不同）
SUPERPOWERS=$(ls -d ~/.claude/plugins/cache/claude-plugins-official/superpowers/*/ | sort -V | tail -1)
DEST="${SUPERPOWERS}skills/boss-job-hunter"
mkdir -p "$DEST"
cp skill/SKILL.md "$DEST/"
```

重启 Claude Code 后，直接说：
> 帮我在上海找 Java 工程师，薪资 20-30K

---

## 常见问题

**Q: 搜索提示 "Cookie 已失效"**  
A: 依次说"帮我退出登录"和"帮我登录 Boss直聘"，完成重新登录后说"读取 Cookie"。

**Q: 登录时浏览器一直跳回空白页**  
A: 这是 Boss直聘 的反爬检测。请确保使用"帮我登录 Boss直聘"命令打开的 Chrome（会以独立 Profile + 调试模式启动），不要手动打开 Chrome 去登录。

**Q: 说"读取 Cookie"时提示连接失败**  
A: Chrome 调试端口未就绪。重新说"帮我登录 Boss直聘"让 Claude 重新打开浏览器，再登录后读取。

**Q: 搜索没有结果**  
A: 尝试降低 `salary_overlap`（如设为 0.3），或放宽 `hr_active_within_days`（如设为 14）。

**Q: 找不到某个城市**  
A: 目前支持：北京、上海、广州、深圳、杭州、成都、武汉、西安、南京。其他城市默认搜索全国。
