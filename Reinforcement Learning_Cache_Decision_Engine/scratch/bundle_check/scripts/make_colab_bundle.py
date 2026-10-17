"""Build everything needed to run M9 on Google Colab.

    python scripts/make_colab_bundle.py

Writes colab_bundle/rlcache_colab.zip (code + tests + configs + the small dev-seed tabular
results used for comparison) and colab_bundle/M9_dqn_colab.ipynb (the notebook to upload).
Excludes .venv, data, scratch and the large results files.  Prints the zip's SHA-256.
"""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "colab_bundle"
INCLUDE_DIRS = ["src", "scripts", "tests", "configs", "docs"]
INCLUDE_FILES = ["pyproject.toml", "requirements-colab.txt", "IMPLEMENTATION_DECISIONS.md"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "data", "scratch", "results", "colab_bundle"}


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(True)}


CELLS = [
    md("""
# M9 — training the DQN on Google Colab

**What this notebook does.** It runs the reinforcement-learning agent (a small neural network
called a *DQN*) on a simulated cache, checks that the learning code is correct, and then trains
it. Nothing here touches real user data: the workload is synthetic.

**How to use it.** Run the cells **from top to bottom, one at a time** (click a cell, press
Shift+Enter). Read the *"What you should see"* note under each step. If a step says **STOP**,
don't continue — copy the output and send it back.

Use a **CPU** runtime (Runtime ▸ Change runtime type ▸ CPU). A GPU is not needed.
"""),
    md("## Step 0 — look at the machine"),
    code("""
import sys, os, platform
print("Python", sys.version.split()[0], "|", platform.platform())
print("CPU cores available:", os.cpu_count())
import torch
print("PyTorch", torch.__version__, "| CUDA available:", torch.cuda.is_available())
"""),
    md("*What you should see:* a Python version, 2 CPU cores or so, and a PyTorch version. "
       "'CUDA available: False' is fine."),
    md("""
## Step 1 — upload the project
Run the next cell, click **Choose files**, and pick **`rlcache_colab.zip`**
(from the `colab_bundle` folder on your computer).
"""),
    code("""
from google.colab import files
up = files.upload()                      # choose rlcache_colab.zip
import zipfile, hashlib
name = next(iter(up))
print("uploaded:", name, "| SHA-256:", hashlib.sha256(open(name, "rb").read()).hexdigest())
zipfile.ZipFile(name).extractall("/content/rlcache")
%cd /content/rlcache
!ls
"""),
    md("*What you should see:* a SHA-256 string (send it to me so I know which code ran) and a "
       "list including `src`, `scripts`, `tests`."),
    md("## Step 2 — install the few extra packages"),
    code("!pip -q install gymnasium pyyaml scipy pandas matplotlib zstandard pytest"),
    md("*What you should see:* it finishes quietly (a few pip warnings are normal)."),
    md("""
## Step 3 — run the automatic tests
This runs ~230 small checks of the whole project. It takes a few minutes.
Tests that need a real Twitter file are skipped on purpose.
"""),
    code("!python -m pytest -q -W ignore tests/"),
    md("""
*What you should see:* a line like `235 passed, 1 skipped`.
**STOP** if you see `failed` — copy the output and send it back.
"""),
    md("""
## Step 4 — check the learning code is correct (gates C1 and C2)
**C1:** does the PyTorch version compute exactly the same numbers as a plain-numpy
reference I wrote? **C2:** can the learner recover the right answers on five tiny puzzles?
"""),
    code("!python scripts/dqn_checks.py --backend torch"),
    md("""
*What you should see:* many `PASS` lines and finally **ALL CHECKS PASSED**.
**STOP** if it says `SOME CHECKS FAILED` — the cache experiments must not be run.
"""),
    md("""
## Step 5 — check the learner on CartPole (gate C3)
CartPole is a classic benchmark (balance a pole on a cart). It tests the learner, not our
cache. Takes about 10–20 minutes. Success = at least 3 of 5 seeds reach a score ≥ 300.
"""),
    code("!python scripts/dqn_cartpole.py --backend torch --seeds 0 1 2 3 4 --steps 100000"),
    md("""
*What you should see:* one line per seed with a final score (max is 500) and a final line
`seeds with mean return >= 300: N/5`. Need N ≥ 3.
**STOP** if N < 3 — send the output back.
"""),
    md("""
## Step 6 — the development run (this is the real experiment, part 1)
Trains the DQN on 5 development workloads × 3 cache sizes × 2 variants = 30 trainings, then
compares it with random choice. It prints a verdict (PASS / PARTIAL / FAIL) that was fixed in
advance. **This takes roughly 1–2 hours on free Colab.** Keep the tab open. If it
disconnects, just run the cell again — finished work is skipped.
"""),
    code("!python scripts/run_dqn.py --stage dev --backend torch --procs 2"),
    md("""
*What you should see:* lines such as `seed 100 cap 0.01: +14 rows`, then a table
`GATE: U(dqn:main) - U(random:45)` and a **PRE-REGISTERED VERDICT**.
"""),
    md("## Step 7 — save the results (do this before anything else)"),
    code("""
!zip -qr dqn_dev_results.zip results/dqn_dev.csv results/dqn_dev.json results/dqn_ckpt
from google.colab import files
files.download("dqn_dev_results.zip")
"""),
    md("""
Send `dqn_dev_results.zip` and the printed verdict back. **Only if the verdict is PASS or
PARTIAL**, the final evaluation run (Step 8) is allowed — and it may be run only once.
"""),
    md("""
## Step 8 — final evaluation run (ONLY if Step 6 said PASS or PARTIAL; run it once)
10 evaluation workloads × 3 cache sizes × 2 variants = 60 trainings (about 3–4 hours).
Do not change anything in this cell.
"""),
    code("""
# !python scripts/run_dqn.py --stage eval --backend torch --procs 2
# (remove the leading '# ' above to enable, after the Step 6 verdict)
"""),
    code("""
# after Step 8 finishes:
# !zip -qr dqn_eval_results.zip results/dqn_eval.csv results/dqn_ckpt
# from google.colab import files; files.download("dqn_eval_results.zip")
"""),
]


def build_notebook() -> dict:
    return {"cells": CELLS, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"}, "colab": {"provenance": []}},
        "nbformat": 4, "nbformat_minor": 5}


def main():
    OUT.mkdir(exist_ok=True)
    zpath = OUT / "rlcache_colab.zip"
    extra = None
    for cand in (ROOT / "results" / "tabq_dev.csv", ROOT.parent / "New folder" / "results" / "tabq_dev.csv"):
        if cand.exists():
            extra = cand
            break
    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d in INCLUDE_DIRS:
            for p in sorted((ROOT / d).rglob("*")):
                if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_PARTS) \
                        and p.suffix not in (".pyc", ".png"):
                    z.write(p, p.relative_to(ROOT).as_posix())
                    n += 1
        for f in INCLUDE_FILES:
            if (ROOT / f).exists():
                z.write(ROOT / f, f)
                n += 1
        if extra is not None:
            z.write(extra, "results/tabq_dev.csv")
            n += 1
    (OUT / "M9_dqn_colab.ipynb").write_text(json.dumps(build_notebook(), indent=1), encoding="utf-8")
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    print(f"{n} files -> {zpath} ({zpath.stat().st_size/1e6:.2f} MB)")
    print(f"notebook -> {OUT / 'M9_dqn_colab.ipynb'}")
    print(f"zip sha256: {sha}")
    print("tabq_dev.csv included:", extra is not None)


if __name__ == "__main__":
    sys.exit(main())
