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
