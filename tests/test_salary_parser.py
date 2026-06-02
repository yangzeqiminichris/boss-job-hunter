import pytest
from boss_job_hunter.salary_parser import parse_salary


def test_simple_range():
    assert parse_salary("20-30K") == (20, 30)

def test_range_with_bonus():
    assert parse_salary("25-40K·13薪") == (25, 40)

def test_range_with_14_bonus():
    assert parse_salary("15-25K·14薪") == (15, 25)

def test_range_lowercase_k():
    assert parse_salary("20-30k") == (20, 30)

def test_mianyi_returns_none():
    assert parse_salary("面议") is None

def test_empty_returns_none():
    assert parse_salary("") is None

def test_non_standard_returns_none():
    assert parse_salary("薪资待遇优厚") is None
