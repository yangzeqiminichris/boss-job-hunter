import pytest
from boss_job_hunter.models import Job, Company
from boss_job_hunter.filters import (
    salary_overlap_ratio,
    filter_job,
    group_and_sort,
)


def make_job(salary_min=20, salary_max=30, hr_days=3, posted_days=10):
    return Job(
        title="工程师", salary_text="20-30K",
        salary_min=salary_min, salary_max=salary_max,
        hr_active_text="3天前活跃", hr_active_days=hr_days,
        posted_text="10天前发布", posted_days=posted_days,
        url="https://example.com",
    )


# --- salary_overlap_ratio ---

def test_exact_match():
    assert salary_overlap_ratio(20, 30, 20, 30) == pytest.approx(1.0)

def test_full_containment_narrow_job():
    # job 25-26 inside target 20-30 → ratio = 1.0 (uses min range as denominator)
    assert salary_overlap_ratio(20, 30, 25, 26) == pytest.approx(1.0)

def test_full_containment_wide_job():
    # job 10-40 contains target 20-30 → ratio = 1.0
    assert salary_overlap_ratio(20, 30, 10, 40) == pytest.approx(1.0)

def test_partial_overlap_50_percent():
    # target 20-30, job 25-35 → intersection=5, min_range=10 → 0.5
    assert salary_overlap_ratio(20, 30, 25, 35) == pytest.approx(0.5)

def test_no_overlap():
    assert salary_overlap_ratio(20, 30, 35, 50) == pytest.approx(0.0)

def test_partial_overlap_15_25_target_20_30():
    # target 20-30 (range 10), job 15-25 (range 10)
    # intersection = 25-20 = 5, min_range = 10 → 0.5
    assert salary_overlap_ratio(20, 30, 15, 25) == pytest.approx(0.5)


# --- filter_job ---

def test_job_passes_all_filters():
    job = make_job(salary_min=20, salary_max=30, hr_days=3, posted_days=10)
    assert filter_job(job, target_min=20, target_max=30, overlap=0.5,
                      posted_within=30, hr_within=7) is True

def test_job_fails_hr_filter():
    job = make_job(hr_days=14)
    assert filter_job(job, target_min=20, target_max=30, overlap=0.5,
                      posted_within=30, hr_within=7) is False

def test_job_fails_posted_filter():
    job = make_job(posted_days=45)
    assert filter_job(job, target_min=20, target_max=30, overlap=0.5,
                      posted_within=30, hr_within=7) is False

def test_job_fails_salary_filter():
    job = make_job(salary_min=35, salary_max=50)
    assert filter_job(job, target_min=20, target_max=30, overlap=0.5,
                      posted_within=30, hr_within=7) is False


# --- group_and_sort ---

def test_same_company_grouped():
    c1 = Company(name="A", size="100-499人", size_order=3,
                 industry="互联网", funding="已上市",
                 jobs=[make_job(), make_job()])
    result = group_and_sort([c1], sort_by="hr_active")
    assert len(result) == 1
    assert len(result[0].jobs) == 2

def test_sort_by_company_size():
    small = Company(name="小", size="0-20人", size_order=1,
                    industry="IT", funding="未融资", jobs=[make_job()])
    big = Company(name="大", size="10000人以上", size_order=5,
                  industry="IT", funding="已上市", jobs=[make_job()])
    result = group_and_sort([small, big], sort_by="company_size")
    assert result[0].name == "大"
