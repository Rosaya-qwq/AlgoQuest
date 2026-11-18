import pytest

from bot.services import stars
from bot.services.stars import (
    ProblemId, extract_problem_ids, format_star_pages, list_stars, normalize_problem_id,
    parse_star_args, record_solution_message, solution_message_problem, update_star,
)


@pytest.fixture(autouse=True)
def isolated_bookmarks(monkeypatch, tmp_path):
    monkeypatch.setattr(stars, "STAR_DB_PATH", tmp_path / "stars.sqlite3")


@pytest.mark.parametrize("raw, canonical", [
    ("CF2062A", "CF2062A"), ("cf 2062 a", "CF2062A"), ("2062a", "CF2062A"),
    ("CF1733D2", "CF1733D2"), ("AT_arc017_1", "AT_arc017_1"),
    ("ATabc350_a", "AT_abc350_a"), ("arc017_1", "AT_arc017_1"),
    ("atc001_a", "AT_atc001_a"), ("AT_dp_a", "AT_dp_a"),
    ("AT_tessoku_book_a", "AT_tessoku_book_a"),
    ("https://codeforces.com/contest/2062/problem/A", "CF2062A"),
    ("https://codeforces.com/gym/102900/problem/A1", "CF102900A1"),
    ("https://www.luogu.com.cn/problem/solution/AT_arc017_1?orderBy=time", "AT_arc017_1"),
    ("https://atcoder.jp/contests/arc017/tasks/arc017_1?lang=en", "AT_arc017_1"),
])
def test_supported_problem_ids_and_urls(raw, canonical):
    assert normalize_problem_id(raw).canonical == canonical


@pytest.mark.parametrize("raw", [
    "CF0A", "CF001A", "CF2062", "CF2062AA", "CF2062A9999", "CFwrong_id",
    "AT_abc350", "AT_arc017_", "AT__arc017_1", "AT_arc017_а", "题号", "", "+CF1A",
    "https://codeforces.com.evil.example/contest/1/problem/A",
    "https://www.luogu.com.cn/problem/P1000", "CF1A CF2B",
])
def test_invalid_problem_ids_are_rejected(raw):
    assert normalize_problem_id(raw) is None


def test_reference_deduplicates_repeated_ids_and_exposes_ambiguity():
    text = "原题：CF2062A，rating 800\n链接：https://codeforces.com/problemset/problem/2062/A"
    assert extract_problem_ids(text) == [ProblemId("cf", "2062A")]
    assert extract_problem_ids("原题：ATarc017_1；链接 https://atcoder.jp/contests/arc017/tasks/arc017_1") == [ProblemId("at", "arc017_1")]
    assert len(extract_problem_ids("CF2062A 与 AT_arc017_1")) == 2
    assert extract_problem_ids("https://evil.example/problem/CF1A") == []


def test_bookmarks_are_persistent_individual_and_idempotent():
    cf, at = ProblemId("cf", "2062A"), ProblemId("at", "arc017_1")
    assert update_star("100", cf, add=True)
    assert not update_star("100", cf, add=True)
    assert update_star("200", at, add=True)
    assert list_stars("100") == [cf]
    assert list_stars("200") == [at]
    assert not update_star("100", at, add=False)
    assert update_star("100", cf, add=False)
    assert not list_stars("100")
    assert list_stars("200") == [at]


def test_image_solution_reference_survives_new_connections_and_is_scoped_to_bot():
    problem = ProblemId("at", "arc017_1")
    record_solution_message("bot1", 12345, problem)
    assert solution_message_problem("bot1", "12345") == problem
    assert solution_message_problem("bot2", "12345") is None


def test_star_operations_and_list_pagination():
    assert parse_star_args(" - CF2062A ") == ("-", "CF2062A")
    assert parse_star_args("+AT_arc017_1") == ("+", "AT_arc017_1")
    assert parse_star_args("CF1A") == ("+", "CF1A")
    assert parse_star_args("-") == ("-", "")
    problems = [ProblemId("cf", f"{i}A") for i in range(1, 101)]
    pages = format_star_pages(problems)
    assert len(pages) > 1
    assert all(len(page) <= 1800 for page in pages)
    assert "100. CF100A\n" in pages[-1]
