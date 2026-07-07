from __future__ import annotations

from asu_june_bot.packaging import preflight
from asu_june_bot.packaging.preflight import CheckResult


def test_check_result_optional_warning_is_not_required_failure() -> None:
    results = [
        CheckResult("required_ok", "ok", "ok", required=True),
        CheckResult("optional_missing", "warn", "missing", required=False),
    ]
    assert preflight.has_required_failures(results) is False


def test_required_error_is_failure() -> None:
    results = [CheckResult("docker", "error", "missing", required=True)]
    assert preflight.has_required_failures(results) is True


def test_format_results_marks_required_and_optional() -> None:
    text = preflight.format_results([
        CheckResult("docker", "ok", "Docker version 1"),
        CheckResult("gigaam", "warn", "not installed", required=False),
        CheckResult("ollama", "error", "unavailable"),
    ])
    assert "[OK] docker (required) - Docker version 1" in text
    assert "[WARN] gigaam (optional) - not installed" in text
    assert "[FAIL] ollama (required) - unavailable" in text


def test_check_ollama_requires_embedding_and_chat_models(monkeypatch) -> None:
    monkeypatch.setattr(preflight, "_ollama_tags", lambda _url, timeout_sec: ["bge-m3"])
    results = preflight.check_ollama(
        base_url="http://ollama.test",
        embedding_model="bge-m3",
        chat_model="qwen3.5:4b",
    )
    by_name = {result.name: result for result in results}
    assert by_name["ollama_api"].status == "ok"
    assert by_name["embedding_model"].status == "ok"
    assert by_name["chat_model"].status == "error"
    assert "qwen3.5:4b missing" in by_name["chat_model"].detail


def test_check_ollama_unavailable_returns_single_error(monkeypatch) -> None:
    def fail(_url: str, timeout_sec: int):
        raise RuntimeError("boom")

    monkeypatch.setattr(preflight, "_ollama_tags", fail)
    results = preflight.check_ollama(base_url="http://ollama.test")
    assert len(results) == 1
    assert results[0].name == "ollama_api"
    assert results[0].status == "error"
    assert "boom" in results[0].detail


def test_run_preflight_docker_mode(monkeypatch) -> None:
    monkeypatch.setattr(preflight, "check_python", lambda: CheckResult("python", "ok", "3.12"))
    monkeypatch.setattr(
        preflight,
        "check_command",
        lambda name, command, required=True: CheckResult(name, "ok", "ok", required),
    )
    monkeypatch.setattr(preflight, "check_ollama", lambda *args, **kwargs: [])
    results = preflight.run_preflight(mode="docker")
    assert [result.name for result in results] == [
        "python",
        "docker",
        "docker_compose",
        "ffmpeg_host",
    ]
    assert results[-1].required is False


def test_run_preflight_local_mode(monkeypatch) -> None:
    monkeypatch.setattr(preflight, "check_python", lambda: CheckResult("python", "ok", "3.12"))
    monkeypatch.setattr(
        preflight,
        "check_command",
        lambda name, command, required=True: CheckResult(name, "ok", "ok", required),
    )
    monkeypatch.setattr(
        preflight,
        "check_import",
        lambda module, label=None, required=False: CheckResult(label or module, "ok", "ok", required),
    )
    monkeypatch.setattr(preflight, "check_ollama", lambda *args, **kwargs: [])
    results = preflight.run_preflight(mode="local")
    assert [result.name for result in results] == ["python", "ffmpeg", "faster_whisper"]
    assert all(result.required for result in results)


def test_run_preflight_rejects_unknown_mode() -> None:
    try:
        preflight.run_preflight(mode="cloud")
    except ValueError as exc:
        assert "mode must be" in str(exc)
    else:
        raise AssertionError("expected ValueError")
