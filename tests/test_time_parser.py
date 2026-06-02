import pytest
from boss_job_hunter.time_parser import parse_active_days, parse_posted_days


def test_just_active():
    assert parse_active_days("刚刚活跃") == 0

def test_today_active():
    assert parse_active_days("今日活跃") == 1

def test_three_days_active():
    assert parse_active_days("3天前活跃") == 3

def test_this_week_active():
    assert parse_active_days("本周活跃") == 7

def test_two_weeks_active():
    assert parse_active_days("2周前活跃") == 14

def test_one_month_active():
    assert parse_active_days("1个月前活跃") == 30

def test_unknown_active_returns_999():
    assert parse_active_days("很久以前") == 999

def test_posted_days_days():
    assert parse_posted_days("3天前发布") == 3

def test_posted_days_weeks():
    assert parse_posted_days("2周前发布") == 14

def test_posted_days_month():
    assert parse_posted_days("1个月前发布") == 30

def test_posted_days_today():
    assert parse_posted_days("今天发布") == 0

def test_posted_unknown_returns_999():
    assert parse_posted_days("很久以前发布") == 999
