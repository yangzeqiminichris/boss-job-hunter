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
