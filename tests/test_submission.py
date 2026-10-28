import asyncio
import json
from pathlib import Path

import httpx
import pytest

from bot.services import submission
from bot.services.problem_random import RenderedProblem
from bot.services.submission import (
    SubmissionReview,
    apply_rating_update,
    calculate_rating_delta,
    estimate_next_accept_delta,
    format_review_message,
    get_rank_entries,
    parse_submit_args,
    problem_snapshot_key,
    repair_rank_stats,
)


def test_parse_submit_args() -> None:
    source, difficulty, solution = parse_submit_args("cf easy sort and two pointers")
    assert source == "cf"
    assert difficulty == "easy"
    assert solution == "sort and two pointers"

    source, difficulty, solution = parse_submit_args("at 中等 动态规划")
    assert source == "at"
    assert difficulty == "medium"
    assert solution == "动态规划"

    source, difficulty, solution = parse_submit_args("unknown text")
    assert source is None
    assert difficulty is None
    assert solution == "unknown text"


def test_rating_delta_rewards_good_submission_more_than_bad_submission() -> None:
    good = calculate_rating_delta(
        old_rating=0,
        difficulty_key="medium",
        problem_rating=2100,
        score=0.9,
        confidence=0.9,
        accepted=True,
        previous_count=0,
    )
    bad = calculate_rating_delta(
        old_rating=0,
        difficulty_key="medium",
        problem_rating=2100,
        score=0.2,
        confidence=0.9,
        accepted=False,
        previous_count=0,
    )

    assert good > 0
    assert bad == 0
    assert good > bad


def test_rating_delta_uses_problem_rating_inside_same_difficulty() -> None:
    low_problem = calculate_rating_delta(
        old_rating=1700,
        difficulty_key="medium",
        problem_rating=1800,
        score=0.65,
        confidence=0.8,
        accepted=True,
        previous_count=0,
    )
    high_problem = calculate_rating_delta(
        old_rating=1700,
        difficulty_key="medium",
        problem_rating=2300,
        score=0.65,
        confidence=0.8,
        accepted=True,
        previous_count=0,
    )

    assert high_problem > low_problem


def test_rating_delta_caps_positive_gain_when_user_rating_exceeds_problem_rating() -> None:
    delta = calculate_rating_delta(
        old_rating=2600,
        difficulty_key="easy",
        problem_rating=1500,
        score=1.0,
        confidence=1.0,
        accepted=True,
        previous_count=0,
    )

    assert 0 < delta <= 5


def test_rating_delta_rewards_challenging_problem_gap() -> None:
    even_problem = calculate_rating_delta(
        old_rating=1600,
        difficulty_key="medium",
        problem_rating=1600,
        score=0.75,
        confidence=0.9,
        accepted=True,
        previous_count=0,
    )
    harder_problem = calculate_rating_delta(
        old_rating=1600,
        difficulty_key="medium",
        problem_rating=1800,
        score=0.75,
        confidence=0.9,
        accepted=True,
        previous_count=0,
    )

    assert harder_problem >= even_problem * 1.35


def test_rejected_submission_does_not_change_rating_and_reports_next_estimate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    problem = RenderedProblem(
        contest_id=1,
        index="A",
        rating=1700,
        tags=["dp"],
        original_name="Hidden",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image="data/codeforces/rendered/1_A/combined.png",
        samples_image="data/codeforces/rendered/1_A/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
    )
    review = SubmissionReview(
        verdict="WRONG_ANSWER",
        score=0.2,
        confidence=0.8,
        sample_simulation="bad",
        extra_tests=["bad1"],
        proof_check="bad",
        complexity_check="ok",
        issues=["wrong transition"],
        suggestions=["fix transition"],
        summary="bad",
    )

    update = apply_rating_update(
        user_id="123",
        difficulty_key="easy",
        problem=problem,
        review=review,
    )

    assert update.delta == 0
    assert update.new_rating == update.old_rating
    assert update.total_submissions == 1
    assert update.total_solved == 0
    assert update.next_accept_delta is not None
    assert update.next_accept_delta > 0


def test_estimate_next_accept_delta_uses_attempt_after_rejection() -> None:
    first_accept = calculate_rating_delta(
        old_rating=1500,
        difficulty_key="easy",
        problem_rating=1700,
        score=0.9,
        confidence=0.9,
        accepted=True,
        previous_count=0,
    )
    next_accept = estimate_next_accept_delta(
        old_rating=1500,
        difficulty_key="easy",
        problem_rating=1700,
        previous_count=1,
        confidence=0.65,
    )

    assert 0 < next_accept < first_accept


def test_apply_rating_update_increments_problem_counter(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    problem = RenderedProblem(
        contest_id=1,
        index="A",
        rating=1500,
        tags=["dp"],
        original_name="Hidden",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image="data/codeforces/rendered/1_A/combined.png",
        samples_image="data/codeforces/rendered/1_A/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
    )
    review = SubmissionReview(
        verdict="ACCEPTED",
        score=0.9,
        confidence=0.8,
        sample_simulation="ok",
        extra_tests=["ok1", "ok2"],
        proof_check="ok",
        complexity_check="ok",
        issues=[],
        suggestions=[],
        summary="ok",
    )

    update = apply_rating_update(
        user_id="123",
        difficulty_key="easy",
        problem=problem,
        review=review,
    )

    assert update.problem_count == 1
    assert update.difficulty_solved_count == 1
    assert update.total_submissions == 1
    assert update.total_solved == 1
    assert update.new_rating > update.old_rating


def test_atcoder_acceptance_is_included_in_rank_difficulty_counts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    problem = RenderedProblem(
        contest_id=0,
        index="abc001_a",
        rating=800,
        tags=[],
        original_name="Hidden",
        url="https://atcoder.jp/contests/abc001/tasks/abc001_a",
        difficulty="easy",
        statement_image="data/atcoder/rendered/at_abc001_a/combined.png",
        samples_image="data/atcoder/rendered/at_abc001_a/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
        source="at",
    )
    review = SubmissionReview(
        verdict="ACCEPTED",
        score=0.9,
        confidence=0.8,
        sample_simulation="ok",
        extra_tests=[],
        proof_check="ok",
        complexity_check="ok",
        issues=[],
        suggestions=[],
        summary="ok",
    )

    apply_rating_update(
        user_id="123",
        source="at",
        difficulty_key="easy",
        problem=problem,
        review=review,
    )

    entry = get_rank_entries()[0]

    assert entry["difficulty_solved_counts"]["easy"] == 1
    assert entry["source_solved_counts"]["at"]["easy"] == 1
    assert entry["total_solved"] == 1


def test_accepted_submission_without_rating_eligibility_keeps_rating(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    problem = RenderedProblem(
        contest_id=1,
        index="A",
        rating=1500,
        tags=["dp"],
        original_name="Hidden",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image="data/codeforces/rendered/1_A/combined.png",
        samples_image="data/codeforces/rendered/1_A/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
    )
    review = SubmissionReview(
        verdict="ACCEPTED",
        score=0.9,
        confidence=0.8,
        sample_simulation="ok",
        extra_tests=["ok1", "ok2"],
        proof_check="ok",
        complexity_check="ok",
        issues=[],
        suggestions=[],
        summary="ok",
    )

    update = apply_rating_update(
        user_id="123",
        difficulty_key="easy",
        problem=problem,
        review=review,
        rating_eligible=False,
        no_rating_reason="本题一血已产生；本次只返回判题结果，不增加 rating。",
    )

    assert update.delta == 0
    assert update.new_rating == update.old_rating
    assert update.rating_eligible is False
    assert update.rating_awarded is False
    assert update.problem_count == 1
    assert update.difficulty_solved_count == 1
    assert update.total_submissions == 1
    assert update.total_solved == 1

    message = format_review_message(
        difficulty_key="easy",
        problem=problem,
        review=review,
        rating_update=update,
    )

    assert "本题一血已产生" in message
    assert "不增加 rating" in message


def test_remove_rank_user_deletes_bot_pollution(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    submission._save_stats(
        {
            "users": {
                "bot": {"total_solved": 1, "difficulty_solved_counts": {"easy": 1}},
                "user": {"total_solved": 1, "difficulty_solved_counts": {"easy": 1}},
            }
        }
    )

    assert submission.remove_rank_user("bot")
    assert submission.remove_rank_user("missing") is False
    assert set(submission._load_stats()["users"]) == {"user"}


def test_remove_invalid_rank_users_deletes_non_numeric_uid(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    submission._save_stats(
        {
            "users": {
                "12345": {"total_solved": 1, "difficulty_solved_counts": {"easy": 1}},
                "蓝毛": {"total_solved": 1, "difficulty_solved_counts": {"easy": 1}},
                "abc123": {"total_solved": 1, "difficulty_solved_counts": {"easy": 1}},
            }
        }
    )

    assert set(submission.remove_invalid_rank_users()) == {"蓝毛", "abc123"}
    assert set(submission._load_stats()["users"]) == {"12345"}


def test_problem_snapshot_key_distinguishes_same_problem_rerender() -> None:
    first_problem = RenderedProblem(
        contest_id=1,
        index="A",
        rating=1500,
        tags=["dp"],
        original_name="Hidden",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image="data/codeforces/rendered/1_A/combined.png",
        samples_image="data/codeforces/rendered/1_A/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
    )
    second_problem = RenderedProblem(
        contest_id=1,
        index="A",
        rating=1500,
        tags=["dp"],
        original_name="Hidden",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image="data/codeforces/rendered/1_A_new/combined.png",
        samples_image="data/codeforces/rendered/1_A_new/combined.png",
        generated_at="2026-05-31T00:00:00+00:00",
    )

    first_key = problem_snapshot_key("easy", first_problem)
    second_key = problem_snapshot_key("easy", second_problem)

    assert first_problem.key == second_problem.key
    assert first_key != second_key


def test_problem_attempt_count_resets_when_problem_changes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    first_problem = RenderedProblem(
        contest_id=1,
        index="A",
        rating=1500,
        tags=["dp"],
        original_name="Hidden",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image="data/codeforces/rendered/1_A/combined.png",
        samples_image="data/codeforces/rendered/1_A/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
    )
    second_problem = RenderedProblem(
        contest_id=2,
        index="B",
        rating=1500,
        tags=["dp"],
        original_name="Hidden",
        url="https://codeforces.com/problemset/problem/2/B",
        difficulty="easy",
        statement_image="data/codeforces/rendered/2_B/combined.png",
        samples_image="data/codeforces/rendered/2_B/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
    )
    review = SubmissionReview(
        verdict="WRONG_ANSWER",
        score=0.2,
        confidence=0.8,
        sample_simulation="bad",
        extra_tests=[],
        proof_check="bad",
        complexity_check="ok",
        issues=[],
        suggestions=[],
        summary="bad",
    )

    first_update = apply_rating_update(
        user_id="123",
        difficulty_key="easy",
        problem=first_problem,
        review=review,
    )
    second_same_problem_update = apply_rating_update(
        user_id="123",
        difficulty_key="easy",
        problem=first_problem,
        review=review,
    )
    new_problem_update = apply_rating_update(
        user_id="123",
        difficulty_key="easy",
        problem=second_problem,
        review=review,
    )

    assert first_update.problem_count == 1
    assert second_same_problem_update.problem_count == 2
    assert new_problem_update.problem_count == 1


def test_format_review_message_hides_simulation_process(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    problem = RenderedProblem(
        contest_id=1,
        index="A",
        rating=1500,
        tags=[],
        original_name="Hidden",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image="data/codeforces/rendered/1_A/combined.png",
        samples_image="data/codeforces/rendered/1_A/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
    )
    review = SubmissionReview(
        verdict="ACCEPTED",
        score=0.7,
        confidence=0.8,
        sample_simulation="hidden sample process",
        extra_tests=["hidden extra process"],
        proof_check="证明思路足够",
        complexity_check="复杂度匹配",
        issues=[],
        suggestions=[],
        summary="核心思路正确",
    )
    update = apply_rating_update(
        user_id="123",
        difficulty_key="easy",
        problem=problem,
        review=review,
    )

    message = format_review_message(
        difficulty_key="easy",
        problem=problem,
        review=review,
        rating_update=update,
    )

    assert "hidden sample process" not in message
    assert "hidden extra process" not in message
    assert "样例模拟" not in message
    assert "额外模拟" not in message
    assert "证明思路足够" not in message
    assert "证明检查" not in message
    assert "复杂度匹配" not in message
    assert "核心思路正确" not in message
    assert "复杂度：已检查。" in message


def test_format_review_message_hides_specific_failure_details(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    problem = RenderedProblem(
        contest_id=1,
        index="A",
        rating=1500,
        tags=[],
        original_name="Hidden",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image="data/codeforces/rendered/1_A/combined.png",
        samples_image="data/codeforces/rendered/1_A/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
    )
    review = SubmissionReview(
        verdict="WRONG_ANSWER",
        score=0.4,
        confidence=0.8,
        sample_simulation="",
        extra_tests=[],
        proof_check="关键性质缺证明",
        complexity_check="复杂度结论不明确",
        issues=["贪心依据不成立"],
        suggestions=["需要检查贪心选择是否总能保留最优解"],
        summary="当前思路链条有断点",
    )
    update = apply_rating_update(
        user_id="123",
        difficulty_key="easy",
        problem=problem,
        review=review,
    )

    message = format_review_message(
        difficulty_key="easy",
        problem=problem,
        review=review,
        rating_update=update,
    )

    assert "建议：" not in message
    assert "需要检查：" not in message
    assert "证明检查" not in message
    assert "主要问题" not in message
    assert "当前思路链条有断点" not in message
    assert "问题定位" in message
    assert "关键性质缺证明" in message
    assert "贪心依据不成立" in message
    assert "正确做法是" not in message
    assert "可能的问题类别" in message
    assert "关键性质或证明说明不足" in message
    assert "复杂度或优化说明不足" in message


def test_format_review_message_can_show_safe_public_feedback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    problem = RenderedProblem(
        contest_id=1,
        index="A",
        rating=1500,
        tags=[],
        original_name="Hidden",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image="data/codeforces/rendered/1_A/combined.png",
        samples_image="data/codeforces/rendered/1_A/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
    )
    review = SubmissionReview(
        verdict="INCOMPLETE",
        score=0.4,
        confidence=0.8,
        sample_simulation="",
        extra_tests=[],
        proof_check="",
        complexity_check="",
        issues=[],
        suggestions=[],
        summary="",
        safe_feedback=[
            "你只写了二分答案，但没有说明 check 判断依赖哪些信息。",
            "正确做法是使用某个关键结构。",
        ],
    )
    update = apply_rating_update(
        user_id="123",
        difficulty_key="easy",
        problem=problem,
        review=review,
    )

    message = format_review_message(
        difficulty_key="easy",
        problem=problem,
        review=review,
        rating_update=update,
    )

    assert "你只写了二分答案，但没有说明 check 判断依赖哪些信息。" in message
    assert "某个关键结构" not in message


def test_review_prompt_uses_json_payload_without_history() -> None:
    problem = RenderedProblem(
        contest_id=1,
        index="A",
        rating=1500,
        tags=["dp"],
        original_name="Hidden",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image="data/codeforces/rendered/1_A/combined.png",
        samples_image="data/codeforces/rendered/1_A/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
    )

    payload = json.loads(submission._build_review_prompt(problem, "statement", "idea"))

    assert payload["submission"] == "idea"
    assert payload["history"] == []
    assert "忽略历史上下文" in payload["history_policy"]
    assert "简体中文" in payload["history_policy"]
    assert payload["problem"]["rating"] == 1500


def test_review_prompt_includes_optional_tutorial_reference() -> None:
    problem = RenderedProblem(
        contest_id=1383,
        index="C",
        rating=1600,
        tags=["dsu"],
        original_name="String Transformation 1",
        url="https://codeforces.com/problemset/problem/1383/C",
        difficulty="easy",
        statement_image="data/codeforces/rendered/1383_C/combined.png",
        samples_image="data/codeforces/rendered/1383_C/combined.png",
        generated_at="2026-05-30T00:00:00+00:00",
        tutorial_url="https://codeforces.com/blog/entry/80562",
    )

    payload = json.loads(
        submission._build_review_prompt(
            problem,
            "statement",
            "idea",
            tutorial_text="official editorial section",
        )
    )

    assert payload["tutorial"]["url"] == "https://codeforces.com/blog/entry/80562"
    assert payload["tutorial"]["content"] == "official editorial section"
    assert "提高置信度" in payload["tutorial"]["policy"]
    assert "不能泄露" in payload["tutorial"]["policy"]
    assert "safe_feedback" in payload["output_schema"]


def test_extract_json_object_accepts_fenced_and_noisy_response() -> None:
    fenced = submission._extract_json_object('```json\n{"verdict":"ACCEPTED"}\n```')
    noisy = submission._extract_json_object('前缀说明\n{"verdict":"WRONG_ANSWER","score":0.2}\n后缀')

    assert fenced["verdict"] == "ACCEPTED"
    assert noisy["verdict"] == "WRONG_ANSWER"


def test_parse_review_payload_normalizes_inconsistent_verdict() -> None:
    low_score_accept = submission._parse_review_payload(
        {"verdict": "ACCEPTED", "score": 0.4, "confidence": 0.9}
    )
    high_score_reject = submission._parse_review_payload(
        {"verdict": "INCOMPLETE", "score": 0.9, "confidence": 0.8}
    )

    assert low_score_accept.verdict == "INCOMPLETE"
    assert not low_score_accept.accepted
    assert high_score_reject.verdict == "INCOMPLETE"
    assert not high_score_reject.accepted


def _passing_review_payload() -> dict:
    return {
        "verdict": "ACCEPTED", "score": 0.95, "confidence": 0.95,
        "checks": {key: "PASS" for key in (
            "understanding", "key_logic", "samples", "extra_tests", "proof", "complexity",
        )},
        "extra_tests": ["额外数据一一致。", "额外数据二一致。"],
    }


def test_accept_requires_all_checks_and_two_extra_tests() -> None:
    payload = _passing_review_payload()
    assert submission._parse_review_payload(payload).accepted
    del payload["checks"]
    assert not submission._parse_review_payload(payload).accepted
    payload = _passing_review_payload()
    payload["extra_tests"] = ["只有一组数据。"]
    assert not submission._parse_review_payload(payload).accepted


@pytest.mark.parametrize("key", ["understanding", "key_logic", "samples", "extra_tests", "proof", "complexity"])
def test_failed_or_unknown_checks_cannot_be_accepted(key: str) -> None:
    for value in ("FAIL", "UNKNOWN", "", None, []):
        payload = _passing_review_payload()
        payload["checks"][key] = value
        assert not submission._parse_review_payload(payload).accepted


def test_correct_outline_can_omit_routine_proof() -> None:
    payload = _passing_review_payload()
    payload["checks"]["proof"] = "NOT_APPLICABLE"
    assert submission._parse_review_payload(payload).accepted


def test_low_confidence_accept_is_uncertain() -> None:
    payload = _passing_review_payload()
    payload["confidence"] = 0.3
    result = submission._parse_review_payload(payload)
    assert result.verdict == "UNCERTAIN"
    assert not result.accepted


def test_downgraded_accept_does_not_publish_success_feedback() -> None:
    payload = _passing_review_payload()
    payload["checks"]["proof"] = "FAIL"
    payload["safe_feedback"] = ["本次提交通过。"]
    payload["summary"] = "本次提交通过。"
    review = submission._parse_review_payload(payload)
    assert not review.accepted
    assert "本次提交通过。" not in review.safe_feedback
    assert review.summary != payload["summary"]
    assert any("证明思路" in item for item in review.safe_feedback)


def test_judge_request_uses_json_thinking_and_retries_truncation(monkeypatch) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "length" if len(calls) == 1 else "stop",
            "message": {"content": None if len(calls) == 1 else '{"verdict":"INCOMPLETE"}'},
        }]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(submission.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_JUDGE_MAX_TOKENS", "65536")
    result = asyncio.run(submission._chat_for_submission("只评审本次提交"))
    assert json.loads(result)["verdict"] == "INCOMPLETE"
    assert [body["max_tokens"] for body in calls] == [65536, 131072]
    assert calls[0]["thinking"] == {"type": "enabled"}
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["reasoning_effort"] == "high"
    assert calls[0]["messages"] == calls[1]["messages"]


def test_submission_system_prompt_requires_simplified_chinese() -> None:
    assert "简体中文" in submission._SUBMISSION_SYSTEM_PROMPT


def test_submission_default_model_is_flash() -> None:
    assert submission.DEFAULT_SUBMISSION_MODEL == "deepseek-flash"


def test_deepseek_base_url_empty_value_uses_official_default(monkeypatch) -> None:
    from bot.services.deepseek import deepseek_base_url

    monkeypatch.setenv("DEEPSEEK_BASE_URL", "")

    assert deepseek_base_url() == "https://api.deepseek.com"


def test_deepseek_base_url_requires_http_protocol(monkeypatch) -> None:
    from bot.services.deepseek import deepseek_base_url

    monkeypatch.setenv("DEEPSEEK_BASE_URL", "api.deepseek.com")

    try:
        deepseek_base_url()
    except RuntimeError as exc:
        assert "http:// 或 https://" in str(exc)
    else:
        raise AssertionError("base URL without protocol should be rejected")


def test_rank_entries_include_solved_counts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    submission._save_stats(
        {
            "users": {
                "10001": {
                    "rating": 1234.5,
                    "total_solved": 2,
                    "difficulty_solved_counts": {
                        "check-in": 1,
                        "easy": 1,
                        "medium": 0,
                        "hard": 0,
                        "impossible": 0,
                    },
                },
                "10002": {
                    "rating": 1400,
                    "total_solved": 0,
                    "difficulty_solved_counts": {},
                },
            }
        }
    )

    entries = get_rank_entries()

    assert [entry["user_id"] for entry in entries] == ["10001"]
    assert entries[0]["difficulty_solved_counts"]["check-in"] == 1
    assert entries[0]["difficulty_solved_counts"]["easy"] == 1
    assert entries[0]["solved_rank_key"] == "000000000000000000000001000001"


def test_repair_rank_stats_recomputes_totals_from_sources(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    submission._save_stats(
        {
            "users": {
                "10001": {
                    "rating": 0,
                    "ratings": {"cf": 10, "at": 20},
                    "total_solved": 0,
                    "difficulty_solved_counts": {},
                    "source_solved_counts": {
                        "cf": {"check-in": 1, "easy": 0, "medium": 0, "hard": 0, "impossible": 0},
                        "at": {"check-in": 0, "easy": 2, "medium": 1, "hard": 0, "impossible": 0},
                    },
                }
            }
        }
    )

    assert repair_rank_stats()
    user = submission._load_stats()["users"]["10001"]

    assert user["difficulty_solved_counts"] == {
        "check-in": 1,
        "easy": 2,
        "medium": 1,
        "hard": 0,
        "impossible": 0,
    }
    assert user["total_solved"] == 4


def test_rank_entries_sort_by_solved_vector_and_share_rank_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(submission, "USER_STATS_PATH", tmp_path / "users.json")
    submission._save_stats(
        {
            "users": {
                "low": {
                    "rating": 9999,
                    "total_solved": 20,
                    "difficulty_solved_counts": {
                        "check-in": 20,
                        "easy": 0,
                        "medium": 0,
                        "hard": 0,
                        "impossible": 0,
                    },
                },
                "high": {
                    "rating": 1,
                    "total_solved": 1,
                    "difficulty_solved_counts": {
                        "check-in": 0,
                        "easy": 0,
                        "medium": 0,
                        "hard": 0,
                        "impossible": 1,
                    },
                },
                "same": {
                    "rating": 2,
                    "total_solved": 1,
                    "difficulty_solved_counts": {
                        "check-in": 0,
                        "easy": 0,
                        "medium": 0,
                        "hard": 0,
                        "impossible": 1,
                    },
                },
            }
        }
    )

    entries = get_rank_entries()

    assert [entry["user_id"] for entry in entries] == ["high", "same", "low"]
    assert entries[0]["solved_rank_key"] == entries[1]["solved_rank_key"]
    assert entries[0]["solved_rank_key"] > entries[2]["solved_rank_key"]


def test_legacy_stats_migrate_to_zero_base_and_keep_only_latest_history(
    monkeypatch,
    tmp_path: Path,
) -> None:
    stats_path = tmp_path / "users.json"
    monkeypatch.setattr(submission, "USER_STATS_PATH", stats_path)
    stats_path.write_text(
        json.dumps(
            {
                "users": {
                    "123": {
                        "rating": 1120.5,
                        "total_submissions": 2,
                        "total_solved": 1,
                        "history": [
                            {
                                "old_rating": 1000,
                                "new_rating": 1040,
                                "delta": 40,
                            },
                            {
                                "old_rating": 1040,
                                "new_rating": 1120.5,
                                "delta": 80.5,
                            },
                        ],
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    stats = submission._load_stats()
    user = stats["users"]["123"]

    assert stats["rating_base"] == 0
    assert user["rating"] == 120.5
    assert len(user["history"]) == 1
    assert user["history"][0]["old_rating"] == 40
    assert user["history"][0]["new_rating"] == 120.5
    assert user["history"][0]["delta"] == 80.5
