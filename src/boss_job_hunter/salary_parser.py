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
