"""The application package must not be able to reach the generator or answer keys."""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "src" / "mei"


def test_app_never_imports_generator_or_reads_answer_keys():
    offenders = []
    for py in APP.rglob("*.py"):
        src = py.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(n.startswith("mei_synth") for n in names):
                offenders.append(f"{py}: imports {names}")
        for token in ("answer_key", "evaluation/"):
            if token in src:
                offenders.append(f"{py}: mentions '{token}'")
    assert not offenders, offenders
