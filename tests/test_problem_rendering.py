import asyncio
from pathlib import Path

from bot.services import problem_random
from bot.services.problem_random import (
    ProblemRef,
    ensure_all_difficulties_on_startup,
    ensure_difficulty_buffer,
    _extract_tutorial_url,
    _move_notes_after_samples,
    _parse_problem_html,
    _parse_atcoder_problem_html,
    _sanitize_math_delimiters,
    _scope_latex_color_commands,
    _slice_tutorial_for_problem,
    _split_image_placeholders,
    cleanup_unreferenced_rendered_dirs,
    refresh_all_difficulties_on_startup,
)
from bot.services.deepseek import _blocks_to_text, _build_obfuscation_prompt, _parse_markdown_blocks
from bot.services.deepseek import DeepSeekClient
from bot.services.html_render import build_html


def test_parse_problem_html_keeps_unordered_lists_notes_images_and_samples() -> None:
    html = """
    <div class="problem-statement">
      <div class="header">
        <div class="title">A. Hidden Name</div>
        <div class="time-limit">time limit per test: 2 seconds</div>
        <div class="memory-limit">memory limit per test: 256 megabytes</div>
      </div>
      <div>
        <p>You are given a <b>special</b> array.</p>
        <ul>
          <li>Choose one element.</li>
          <li>Erase another element.</li>
        </ul>
        <p>See the diagram <img src="/predownloaded/sample.png"> before answering.</p>
      </div>
      <div class="input-specification">
        <div class="section-title">Input</div>
        <p>The first line contains <span class="math">\\(n\\)</span>.</p>
      </div>
      <div class="note">
        <div class="section-title">Note</div>
        <p>The first sample uses the first operation. <img src="/predownloaded/note.png"></p>
        <ul><li>This bullet belongs to the note.</li></ul>
      </div>
      <div class="sample-test">
        <div class="input"><pre>2
1 2</pre></div>
        <div class="output"><pre>3</pre></div>
      </div>
    </div>
    """

    blocks, samples, images, limits = _parse_problem_html(
        html,
        "https://codeforces.com/problemset/problem/1/A",
    )
    blocks = _split_image_placeholders(
        blocks,
        {
            images[0]["placeholder"]: "data:image/png;base64,AAAA",
            images[1]["placeholder"]: "data:image/png;base64,BBBB",
        },
    )

    assert {"type": "paragraph", "text": "You are given a **special** array."} in blocks
    assert {"type": "list_item", "text": "Choose one element."} in blocks
    assert {"type": "list_item", "text": "Erase another element."} in blocks
    assert any(block.get("type") == "image" and block.get("data_uri") for block in blocks)
    assert limits == {"time_limit": "2 s", "memory_limit": "256 MB"}

    note = next(block for block in blocks if block.get("type") == "note")
    assert {"type": "paragraph", "text": "The first sample uses the first operation."} in note["blocks"]
    assert any(block.get("type") == "image" and block.get("data_uri") for block in note["blocks"])
    assert {"type": "list_item", "text": "This bullet belongs to the note."} in note["blocks"]

    assert samples == [{"input": "2\n1 2", "output": "3"}]


def test_build_html_renders_lists_notes_and_images() -> None:
    html = build_html(
        title="Codeforces Practice",
        meta_items=[
            ("难度", "easy"),
            ("时间", "2 s"),
            ("空间", "256 MB"),
        ],
        blocks=[
            {"type": "paragraph", "text": "Before **important** list."},
            {"type": "list_item", "text": "First unordered item"},
            {"type": "list_item", "text": "Second unordered item"},
            {
                "type": "note",
                "blocks": [
                    {"type": "paragraph", "text": "Important note."},
                    {"type": "ordered_list_item", "text": "First ordered item"},
                ],
            },
            {"type": "image", "data_uri": "data:image/png;base64,AAAA"},
        ],
    )

    assert '<span class="meta-label">难度：</span><span class="meta-value">easy</span>' in html
    assert '<span class="meta-label">时间：</span><span class="meta-value">2 s</span>' in html
    assert '<span class="meta-label">空间：</span><span class="meta-value">256 MB</span>' in html
    assert "题面" not in html
    assert "<strong>important</strong>" in html
    assert "<ul><li>First unordered item</li><li>Second unordered item</li></ul>" in html
    assert '<div class="note"><div class="note-title">说明</div>' in html
    assert "<ol><li>First ordered item</li></ol>" in html
    assert '<img src="data:image/png;base64,AAAA" alt="problem image">' in html


def test_build_html_renders_inline_code() -> None:
    html = build_html(
        title="AtCoder Practice",
        blocks=[
            {"type": "paragraph", "text": "Each query is `1 l r` or `2 x y`."},
        ],
    )

    assert "<code>1 l r</code>" in html
    assert "<code>2 x y</code>" in html


def test_build_html_renders_markdown_emphasis_variants() -> None:
    html = build_html(
        title="AtCoder Practice",
        blocks=[
            {
                "type": "paragraph",
                "text": "**bold** __not bold__ *italic* _not italic_ `1 _ x`",
            },
        ],
    )

    assert "<strong>bold</strong>" in html
    assert "__not bold__" in html
    assert "<strong>not bold</strong>" not in html
    assert "<strong>italic</strong>" in html
    assert "_not italic_" in html
    assert "<em>not italic</em>" not in html
    assert "<code>1 _ x</code>" in html


def test_build_html_keeps_math_inside_bold_markers_renderable() -> None:
    html = build_html(
        title="Codeforces Practice",
        blocks=[
            {
                "type": "paragraph",
                "text": "Distance is *$|x_i-x_j|+|y_i-y_j|$* and *value $d$ matters*.",
            },
        ],
    )

    assert "<em>" not in html
    assert "$|x_i-x_j|+|y_i-y_j|$" in html
    assert "<strong>$|x_i-x_j|+|y_i-y_j|$</strong>" not in html
    assert "<strong>value $d$ matters</strong>" in html


def test_build_html_converts_star_wrapped_variables_back_to_math() -> None:
    html = build_html(
        title="Codeforces Practice",
        blocks=[
            {"type": "paragraph", "text": "There are *n* vertices and **x_i** is important."},
        ],
    )

    assert "$n$" in html
    assert "$x_i$" in html
    assert "<strong>n</strong>" not in html
    assert "<strong>x_i</strong>" not in html


def test_deepseek_markdown_roundtrip_keeps_structural_blocks() -> None:
    markdown = _blocks_to_text(
        [
            {"type": "list_item", "text": "First bullet"},
            {"type": "image", "data_uri": "data:image/png;base64,AAAA"},
            {
                "type": "note",
                "blocks": [
                    {"type": "paragraph", "text": "Inside note."},
                    {"type": "ordered_list_item", "text": "Ordered note item"},
                    {"type": "image", "data_uri": "data:image/png;base64,BBBB"},
                ],
            },
        ]
    )

    assert "- First bullet" in markdown
    assert "[IMG]" in markdown
    assert ":::note" in markdown

    blocks = _parse_markdown_blocks(markdown)
    assert {"type": "list_item", "text": "First bullet"} in blocks
    assert any(block.get("type") == "image" for block in blocks)

    note = next(block for block in blocks if block.get("type") == "note")
    assert {"type": "paragraph", "text": "Inside note."} in note["blocks"]
    assert {"type": "ordered_list_item", "text": "Ordered note item"} in note["blocks"]
    assert any(block.get("type") == "image" for block in note["blocks"])


def test_deepseek_markdown_parser_accepts_hash_heading_levels() -> None:
    blocks = _parse_markdown_blocks("# Statement\n\n### Input\n\n###### Output")

    assert blocks == [
        {"type": "heading", "text": "Statement"},
        {"type": "heading", "text": "Input"},
        {"type": "heading", "text": "Output"},
    ]


def test_deepseek_translation_model_is_independent_from_judge_model(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.delenv("DEEPSEEK_TRANSLATION_MODEL", raising=False)

    client = DeepSeekClient()

    assert client._model == "deepseek-v4-flash"

    monkeypatch.setenv("DEEPSEEK_TRANSLATION_MODEL", "custom-translation-model")
    client = DeepSeekClient()

    assert client._model == "custom-translation-model"


def test_deepseek_judge_solution_defaults_use_pro_only_for_impossible(monkeypatch) -> None:
    from bot.services.deepseek import deepseek_model_for

    for key in (
        "DEEPSEEK_MODEL",
        "DEEPSEEK_JUDGE_MODEL",
        "DEEPSEEK_SOLUTION_MODEL",
        "DEEPSEEK_JUDGE_MODEL_EASY",
        "DEEPSEEK_JUDGE_MODEL_HARD",
        "DEEPSEEK_SOLUTION_MODEL_EASY",
        "DEEPSEEK_SOLUTION_MODEL_HARD",
    ):
        monkeypatch.delenv(key, raising=False)

    assert deepseek_model_for("judge", "easy") == "deepseek-v4-flash"
    assert deepseek_model_for("solution", "medium") == "deepseek-v4-flash"
    assert deepseek_model_for("judge", "hard") == "deepseek-v4-flash"
    assert deepseek_model_for("solution", "hard") == "deepseek-v4-flash"
    assert deepseek_model_for("judge", "impossible") == "deepseek-v4-pro"
    assert deepseek_model_for("solution", "impossible") == "deepseek-v4-pro"


def test_deepseek_obfuscation_prompt_requires_simplified_chinese() -> None:
    prompt = _build_obfuscation_prompt("statement")

    assert "Simplified Chinese" in prompt
    assert "简体中文" in prompt
    assert "_text_" in prompt
    assert "__text__" in prompt
    assert "do not wrap LaTeX formulas" in prompt


def test_sanitize_math_delimiters_removes_extra_dollars() -> None:
    assert _sanitize_math_delimiters("value $$$x+y$$$ end") == "value $x+y$ end"
    assert _sanitize_math_delimiters("value $$x+y$ end") == "value $$x+y$$ end"
    assert _sanitize_math_delimiters("value $x+y$$ end") == "value $$x+y$$ end"
    assert _sanitize_math_delimiters(r"value $x \coloneqq y$ end") == "value $x := y$ end"


def test_scope_latex_color_commands_prevents_color_leakage() -> None:
    text = r"$[1, \color{red}{2}, \color{red}{3}] \rightarrow [1]$"

    assert _scope_latex_color_commands(text) == (
        r"$[1, \textcolor{red}{2}, \textcolor{red}{3}] \rightarrow [1]$"
    )


def test_atcoder_problem_pool_keeps_only_regular_contests(monkeypatch) -> None:
    payload = {
        "fetched_at": problem_random.time.time(),
        "problems": {
            "abc001_a": {"id": "abc001_a", "contest_id": "abc001", "title": "ABC"},
            "arc100_a": {"id": "arc100_a", "contest_id": "arc100", "title": "ARC"},
            "agc001_a": {"id": "agc001_a", "contest_id": "agc001", "title": "AGC"},
            "atc001_a": {"id": "atc001_a", "contest_id": "atc001", "title": "ATC"},
            "typical90_a": {"id": "typical90_a", "contest_id": "typical90", "title": "Other"},
        },
        "models": {
            "abc001_a": {"difficulty": 1500},
            "arc100_a": {"difficulty": 1500},
            "agc001_a": {"difficulty": 1500},
            "atc001_a": {"difficulty": 1500},
            "typical90_a": {"difficulty": 1500},
        },
    }
    monkeypatch.setattr(problem_random, "_load_atcoder_cache", lambda: payload)

    refs = asyncio.run(problem_random._load_atcoder_problem_pool(problem_random.ATCODER_DIFFICULTIES["easy"]))

    assert {ref.atcoder_task_id for ref in refs} == {"abc001_a", "arc100_a", "agc001_a", "atc001_a"}


def test_default_atcoder_rating_ranges_match_codeforces() -> None:
    for key, difficulty in problem_random.DIFFICULTIES.items():
        at_difficulty = problem_random.ATCODER_DIFFICULTIES[key]
        assert at_difficulty.min_rating == difficulty.min_rating
        assert at_difficulty.max_rating == difficulty.max_rating


def test_rating_range_env_parser(monkeypatch) -> None:
    monkeypatch.setenv("CF_RATING_TEST", "3000,inf")
    assert problem_random._env_rating_range("CF_RATING_TEST", 0, 1) == (3000, None)

    monkeypatch.setenv("CF_RATING_TEST", "1200,1800")
    assert problem_random._env_rating_range("CF_RATING_TEST", 0, 1) == (1200, 1800)

    monkeypatch.setenv("CF_RATING_TEST", "bad")
    assert problem_random._env_rating_range("CF_RATING_TEST", 0, 1) == (0, 1)


def test_cookie_header_parses_netscape_cookie_file(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "\n".join(
            [
                "# Netscape HTTP Cookie File",
                ".codeforces.com\tTRUE\t/\tTRUE\t2147483647\tJSESSIONID\tabc",
                "#HttpOnly_.codeforces.com\tTRUE\t/\tTRUE\t2147483647\tcf_clearance\tclear",
                ".atcoder.jp\tTRUE\t/\tTRUE\t2147483647\tREVEL_SESSION\tat",
            ]
        ),
        encoding="utf-8",
    )

    assert problem_random._cookie_header(
        direct_cookie="",
        cookie_file=str(cookie_file),
        domain_hint="codeforces.com",
    ) == "JSESSIONID=abc; cf_clearance=clear"


def test_request_headers_use_env_cookie(monkeypatch) -> None:
    monkeypatch.setattr(problem_random, "CODEFORCES_COOKIE", "a=b; c=d")
    monkeypatch.setattr(problem_random, "CODEFORCES_COOKIES_FILE", "")
    monkeypatch.setattr(problem_random, "CODEFORCES_USER_AGENT", "Test UA")

    headers = problem_random._request_headers_for_source("cf")

    assert headers["User-Agent"] == "Test UA"
    assert headers["Cookie"] == "a=b; c=d"


def test_move_notes_after_samples_keeps_notes_for_the_end() -> None:
    statement, notes = _move_notes_after_samples(
        [
            {"type": "paragraph", "text": "Statement"},
            {"type": "note", "blocks": [{"type": "paragraph", "text": "Note"}]},
            {"type": "paragraph", "text": "More statement"},
        ]
    )

    assert statement == [
        {"type": "paragraph", "text": "Statement"},
        {"type": "paragraph", "text": "More statement"},
    ]
    assert notes == [{"type": "note", "blocks": [{"type": "paragraph", "text": "Note"}]}]


def test_move_notes_after_samples_merges_note_like_blocks() -> None:
    statement, notes = _move_notes_after_samples(
        [
            {"type": "paragraph", "text": "Statement"},
            {"type": "note", "blocks": [{"type": "paragraph", "text": "Note"}]},
            {"type": "note", "blocks": [{"type": "paragraph", "text": "Example"}]},
        ]
    )

    assert statement == [{"type": "paragraph", "text": "Statement"}]
    assert notes == [
        {
            "type": "note",
            "blocks": [
                {"type": "paragraph", "text": "Note"},
                {"type": "paragraph", "text": "Example"},
            ],
        }
    ]


def test_parse_problem_html_treats_examples_section_as_note() -> None:
    html = """
    <div class="problem-statement">
      <div class="header"><div class="title">A. Hidden Name</div></div>
      <div><p>Main statement.</p></div>
      <div>
        <div class="section-title">Examples</div>
        <p>This paragraph explains the examples.</p>
      </div>
      <div class="sample-test">
        <div class="input"><pre>1</pre></div>
        <div class="output"><pre>1</pre></div>
      </div>
    </div>
    """

    blocks, samples, _, _ = _parse_problem_html(html, "https://codeforces.com/problemset/problem/1/A")

    assert {"type": "paragraph", "text": "Main statement."} in blocks
    assert {"type": "heading", "text": "Examples"} not in blocks
    note = next(block for block in blocks if block.get("type") == "note")
    assert {"type": "paragraph", "text": "This paragraph explains the examples."} in note["blocks"]
    assert samples == [{"input": "1", "output": "1"}]


def test_parse_atcoder_problem_html_extracts_samples_and_limits() -> None:
    html = """
    <html><body>
      <p>Time Limit: 2 sec / Memory Limit: 1024 MB</p>
      <div id="task-statement">
        <span class="lang-en">
          <h3>Statement</h3>
          <p>You are given <strong>N</strong> and <em>M</em>.</p>
          <h3>Input</h3>
          <pre>N</pre>
          <h3>Output</h3>
          <p>Print the answer.</p>
          <h3>Sample Input 1</h3>
          <pre>1</pre>
          <h3>Sample Output 1</h3>
          <pre>2</pre>
        </span>
      </div>
    </body></html>
    """

    blocks, samples, _, limits = problem_random._parse_atcoder_problem_html(
        html,
        "https://atcoder.jp/contests/abc001/tasks/abc001_1",
    )

    assert {"type": "paragraph", "text": "You are given $N$ and $M$."} in blocks
    assert {"type": "paragraph", "text": "Sample Input 1"} not in blocks
    assert {"type": "pre", "text": "1"} not in blocks
    assert samples == [{"input": "1", "output": "2"}]
    assert limits == {"time_limit": "2 sec", "memory_limit": "1024 MB"}


def test_parse_atcoder_samples_when_title_and_pre_are_nested() -> None:
    html = """
    <html><body>
      <p>Time Limit: 2 sec / Memory Limit: 1024 MB</p>
      <div id="task-statement">
        <span class="lang-en">
          <h3>Statement</h3>
          <p>Main statement.</p>
          <section><h3>Sample Input 1</h3><div><pre>1 2</pre></div></section>
          <section><h3>Sample Output 1</h3><div><pre>3</pre></div></section>
        </span>
      </div>
    </body></html>
    """

    blocks, samples, _, _ = _parse_atcoder_problem_html(
        html,
        "https://atcoder.jp/contests/abc001/tasks/abc001_1",
    )

    assert {"type": "paragraph", "text": "Main statement."} in blocks
    assert samples == [{"input": "1 2", "output": "3"}]


def test_parse_atcoder_limits_does_not_swallow_statement_text() -> None:
    html = """
    <html><body>
      <div>
        Time Limit: 2 sec / Memory Limit: 1024 MiB
        <div id="task-statement">
          <span class="lang-en">
            <h3>Statement</h3>
            <p>Problem Statement should not become memory limit.</p>
            <p>Each query is <code>1 l r</code>.</p>
          </span>
        </div>
      </div>
    </body></html>
    """

    blocks, _, _, limits = problem_random._parse_atcoder_problem_html(
        html,
        "https://atcoder.jp/contests/abc001/tasks/abc001_1",
    )

    assert limits == {"time_limit": "2 sec", "memory_limit": "1024 MiB"}
    assert {"type": "paragraph", "text": "Each query is `1 l r`."} in blocks


def test_extract_tutorial_url_from_problem_page_materials() -> None:
    html = """
    <html><body>
      <a href="/blog/entry/80562">Tutorial (en)</a>
      <a href="/contest/1383">Contest</a>
    </body></html>
    """

    assert (
        _extract_tutorial_url(html, "https://codeforces.com/problemset/problem/1383/C")
        == "https://codeforces.com/blog/entry/80562"
    )


def test_slice_tutorial_prefers_current_problem_section() -> None:
    problem = ProblemRef(
        contest_id=1383,
        index="C",
        name="String Transformation 1",
        rating=1600,
        tags=[],
    )
    text = (
        "A. Other problem\n"
        + "wrong section " * 200
        + "\nC. String Transformation 1\nThis is the current tutorial section.\n"
        + "details " * 100
    )

    sliced = _slice_tutorial_for_problem(text, problem)

    assert "C. String Transformation 1" in sliced
    assert "This is the current tutorial section." in sliced


def test_cleanup_unreferenced_rendered_dirs(monkeypatch, tmp_path: Path) -> None:
    rendered_dir = tmp_path / "rendered"
    state_dir = tmp_path / "states"
    at_rendered_dir = tmp_path / "at-rendered"
    at_state_dir = tmp_path / "at-states"
    keep_dir = rendered_dir / "1_A"
    drop_dir = rendered_dir / "2_B"
    at_drop_dir = at_rendered_dir / "abc001_a"
    keep_dir.mkdir(parents=True)
    drop_dir.mkdir(parents=True)
    at_drop_dir.mkdir(parents=True)
    keep_image = keep_dir / "combined.png"
    keep_image.write_bytes(b"png")
    (drop_dir / "combined.png").write_bytes(b"png")
    (at_drop_dir / "combined.png").write_bytes(b"png")

    monkeypatch.setattr(problem_random, "RENDERED_DIR", rendered_dir)
    monkeypatch.setattr(problem_random, "STATE_DIR", state_dir)
    monkeypatch.setattr(problem_random, "ATCODER_RENDERED_DIR", at_rendered_dir)
    monkeypatch.setattr(problem_random, "ATCODER_STATE_DIR", at_state_dir)
    problem_random._save_json(
        state_dir / "easy.json",
        {
            "difficulty": "easy",
            "cur_state": {"statement_image": str(keep_image)},
            "next_state": None,
        },
    )

    assert cleanup_unreferenced_rendered_dirs(source="cf") == 1
    assert keep_dir.exists()
    assert not drop_dir.exists()
    assert at_drop_dir.exists()

    assert cleanup_unreferenced_rendered_dirs(source="at") == 1
    assert not at_drop_dir.exists()


def test_refresh_all_difficulties_writes_cur_and_next(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(problem_random, "STATE_DIR", tmp_path / "states")
    monkeypatch.setattr(problem_random, "RENDERED_DIR", tmp_path / "rendered")
    monkeypatch.setattr(problem_random, "ATCODER_STATE_DIR", tmp_path / "at-states")
    monkeypatch.setattr(problem_random, "ATCODER_RENDERED_DIR", tmp_path / "at-rendered")

    async def fake_build_random_problem(difficulty_key: str, exclude_keys=None, source="cf"):
        suffix = "next" if exclude_keys else "cur"
        image_dir = problem_random._rendered_dir_for(source) / f"{source}_{difficulty_key}_{suffix}"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / "combined.png"
        image_path.write_bytes(b"png")
        return problem_random.RenderedProblem(
            contest_id=1,
            index=f"{difficulty_key}_{suffix}",
            rating=1200,
            tags=[],
            original_name="Hidden",
            url="https://codeforces.com/problemset/problem/1/A",
            difficulty=difficulty_key,
            statement_image=str(image_path),
            samples_image=str(image_path),
            generated_at="2026-05-30T00:00:00+00:00",
            source=source,
        )

    monkeypatch.setattr(problem_random, "_build_random_problem", fake_build_random_problem)

    results = asyncio.run(refresh_all_difficulties_on_startup())

    assert all(result == "ok" for result in results.values())
    for source, difficulties in problem_random.DIFFICULTIES_BY_SOURCE.items():
        for difficulty_key in difficulties:
            state = problem_random._load_state(difficulty_key, source)
            assert state["cur_state"]["difficulty"] == difficulty_key
            assert state["cur_state"]["source"] == source
            assert state["next_state"]["difficulty"] == difficulty_key
            assert state["next_state"]["source"] == source


def test_ensure_difficulty_buffer_keeps_existing_slots(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(problem_random, "STATE_DIR", tmp_path / "states")
    monkeypatch.setattr(problem_random, "RENDERED_DIR", tmp_path / "rendered")
    monkeypatch.setattr(problem_random, "ATCODER_STATE_DIR", tmp_path / "at-states")
    monkeypatch.setattr(problem_random, "ATCODER_RENDERED_DIR", tmp_path / "at-rendered")

    current_dir = problem_random.RENDERED_DIR / "cf_current"
    next_dir = problem_random.RENDERED_DIR / "cf_next"
    current_dir.mkdir(parents=True)
    next_dir.mkdir(parents=True)
    current_image = current_dir / "combined.png"
    next_image = next_dir / "combined.png"
    current_image.write_bytes(b"png")
    next_image.write_bytes(b"png")
    current = problem_random.RenderedProblem(
        contest_id=1,
        index="A",
        rating=1200,
        tags=[],
        original_name="Current",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image=str(current_image),
        samples_image=str(current_image),
        generated_at="2026-05-30T00:00:00+00:00",
        source="cf",
        ai_brief="cached solution",
        statement_text="cached statement",
    )
    upcoming = problem_random.RenderedProblem(
        contest_id=2,
        index="B",
        rating=1300,
        tags=[],
        original_name="Next",
        url="https://codeforces.com/problemset/problem/2/B",
        difficulty="easy",
        statement_image=str(next_image),
        samples_image=str(next_image),
        generated_at="2026-05-30T00:00:00+00:00",
        source="cf",
        ai_brief="cached solution",
        statement_text="cached statement",
    )
    problem_random._save_state(
        "easy",
        {"cur_state": problem_random.asdict(current), "next_state": problem_random.asdict(upcoming)},
        "cf",
    )

    async def fail_build_random_problem(*args, **kwargs):
        raise AssertionError("should not render when both slots are valid")

    monkeypatch.setattr(problem_random, "_build_random_problem", fail_build_random_problem)

    ensured_current, ensured_next, changed = asyncio.run(ensure_difficulty_buffer("easy", source="cf"))

    assert not changed
    assert ensured_current.key == current.key
    assert ensured_next.key == upcoming.key


def test_ensure_difficulty_buffer_fills_missing_next(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(problem_random, "STATE_DIR", tmp_path / "states")
    monkeypatch.setattr(problem_random, "RENDERED_DIR", tmp_path / "rendered")
    monkeypatch.setattr(problem_random, "ATCODER_STATE_DIR", tmp_path / "at-states")
    monkeypatch.setattr(problem_random, "ATCODER_RENDERED_DIR", tmp_path / "at-rendered")

    current_dir = problem_random.RENDERED_DIR / "cf_current"
    current_dir.mkdir(parents=True)
    current_image = current_dir / "combined.png"
    current_image.write_bytes(b"png")
    current = problem_random.RenderedProblem(
        contest_id=1,
        index="A",
        rating=1200,
        tags=[],
        original_name="Current",
        url="https://codeforces.com/problemset/problem/1/A",
        difficulty="easy",
        statement_image=str(current_image),
        samples_image=str(current_image),
        generated_at="2026-05-30T00:00:00+00:00",
        source="cf",
        ai_brief="cached solution",
        statement_text="cached statement",
    )
    problem_random._save_state("easy", {"cur_state": problem_random.asdict(current), "next_state": None}, "cf")

    async def fake_build_random_problem(difficulty_key: str, exclude_keys=None, source="cf", **kwargs):
        assert exclude_keys == {current.key}
        image_dir = problem_random.RENDERED_DIR / "cf_next"
        image_dir.mkdir(parents=True)
        image_path = image_dir / "combined.png"
        image_path.write_bytes(b"png")
        return problem_random.RenderedProblem(
            contest_id=2,
            index="B",
            rating=1300,
            tags=[],
            original_name="Next",
            url="https://codeforces.com/problemset/problem/2/B",
            difficulty=difficulty_key,
            statement_image=str(image_path),
            samples_image=str(image_path),
            generated_at="2026-05-30T00:00:00+00:00",
            source=source,
            ai_brief="cached solution",
            statement_text="cached statement",
        )

    monkeypatch.setattr(problem_random, "_build_random_problem", fake_build_random_problem)

    ensured_current, ensured_next, changed = asyncio.run(ensure_difficulty_buffer("easy", source="cf"))

    assert changed
    assert ensured_current.key == current.key
    assert ensured_next.key == "2B"


def test_fetch_problem_html_uses_cloudscraper_fallback(monkeypatch) -> None:
    class FailedResponse:
        text = ""

        def raise_for_status(self) -> None:
            raise RuntimeError("403 challenge")

    class FailedClient:
        async def get(self, *args, **kwargs):
            return FailedResponse()

    async def fake_cloudscraper(url: str) -> str:
        assert "codeforces.com" in url
        return '<div class="problem-statement"><p>ok</p></div>'

    monkeypatch.setattr(problem_random, "CODEFORCES_CLOUDSCRAPER_ENABLED", True)
    monkeypatch.setattr(problem_random, "_fetch_problem_html_with_cloudscraper", fake_cloudscraper)

    html = asyncio.run(
        problem_random._fetch_problem_html(
            FailedClient(),
            ProblemRef(contest_id=1, index="A", name="A", rating=800, tags=[]),
        )
    )

    assert "problem-statement" in html
