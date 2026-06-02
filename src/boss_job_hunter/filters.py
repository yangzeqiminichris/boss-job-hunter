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
