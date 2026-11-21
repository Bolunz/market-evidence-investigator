"""A recording made in one process replays exactly in another: different PYTHONHASHSEED, different
working directory, and a different .env (models/effort), as on a grader's machine."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECORD = """
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from tests.fake_llm import factory
from mei.run import run_investigation
from mei_synth.generate import generate
tmp = Path(sys.argv[2])
g = generate(42, "positive", tmp / "data", tmp / "keys")
run_investigation(g["data_dir"], tmp / "rec", mode="live", cache_path=tmp / "rec" / "llm_cache.jsonl",
                  chat_factory=factory)
"""


def _env(**kw):
    env = {k: v for k, v in os.environ.items() if not k.startswith("MEI_")}
    return {**env, "ANTHROPIC_API_KEY": "", **kw}


@pytest.fixture(scope="module")
def recording(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("rec")
    r = subprocess.run([sys.executable, "-c", RECORD, str(ROOT), str(tmp)], env=_env(PYTHONHASHSEED="1"),
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    return tmp / "rec"


def _verify(run_dir, cwd, **env):
    return subprocess.run([sys.executable, "-m", "mei.cli", "verify-replay", "--run", str(run_dir)],
                          cwd=cwd, env=_env(**env), capture_output=True, text=True, timeout=600)


def test_replay_in_another_process_reproduces_every_output(recording, tmp_path):
    r = _verify(recording, tmp_path, PYTHONHASHSEED="2", MEI_EFFORT_MAIN="high", MEI_MODEL_MAIN="other-model",
                COLUMNS="200")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    for item in ("state.json", "ledger.json", "checks.json", "trace.jsonl", "report.md", "report.html", "LLM calls and tokens",
                 "ledger re-execution"):
        assert f"PASS  {item}" in r.stdout
    assert "FAIL" not in r.stdout


def test_verify_replay_detects_a_changed_output(recording, tmp_path):
    import shutil
    bad = tmp_path / "bad"
    shutil.copytree(recording, bad)
    checks = json.loads((bad / "checks.json").read_text())
    checks[0]["status"] = "flagged" if checks[0]["status"] == "verified" else "verified"
    (bad / "checks.json").write_text(json.dumps(checks, indent=2))
    r = _verify(bad, tmp_path, PYTHONHASHSEED="3", COLUMNS="200")
    assert r.returncode == 1 and "FAIL  checks.json" in r.stdout


def test_live_run_refuses_to_reuse_an_existing_recording(recording, tmp_path):
    from mei.run import RecordingExists, run_investigation
    with pytest.raises(RecordingExists):
        run_investigation(json.loads((recording / "run_meta.json").read_text())["data_dir"], recording,
                          mode="live", cache_path=recording / "llm_cache.jsonl")


def test_cross_platform_float_rounding_is_reported_but_real_differences_fail():
    """Regression from live run 02 replayed on Linux after recording on macOS: p-values differed only
    in their last digits (e.g. 0.0036856349233613003 vs 0.0036856349233613)."""
    from mei.verify import compare_output
    rec = json.dumps({"entries": [{"p_value": 0.0036856349233613003, "status": "verified", "n": 15}]})
    ok, detail = compare_output("ledger.json", rec, rec.replace("0.0036856349233613003", "0.0036856349233613"))
    assert ok and "floating-point rounding" in detail and "1 numbers" in detail
    ok, detail = compare_output("ledger.json", rec, rec.replace("0.0036856349233613003", "0.0036857"))
    assert not ok and "p_value" in detail                       # a real numerical difference
    ok, _ = compare_output("ledger.json", rec, rec.replace('"verified"', '"flagged"'))
    assert not ok
    html = "<p>table 18.09%</p><img src=\"data:image/png;base64,AAAA\">"
    ok, detail = compare_output("report.html", html, html.replace("AAAA", "BBBB"))
    assert ok and "chart images" in detail
    ok, _ = compare_output("report.html", html, html.replace("18.09%", "18.10%").replace("AAAA", "BBBB"))
    assert not ok
