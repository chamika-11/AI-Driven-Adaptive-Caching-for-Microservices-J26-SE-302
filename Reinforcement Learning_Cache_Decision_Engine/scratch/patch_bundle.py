import pathlib

p = pathlib.Path("scripts/make_colab_bundle.py")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    assert s.count(old) == 1, old[:70]
    s = s.replace(old, new)


rep('''def build_notebook() -> dict:''', '''REPAIR_CELLS = [
    md("""
# M9-e — finishing the "repair" experiment on Google Colab

**Background.** On your own PC this experiment was stopped (the PC got too hot) after 20 of 30 work
units were finished. Those finished results are inside the zip (`results/dqn_repair_dev.csv`). This
notebook **only does the remaining 10 units** (seed 116 at 25%, and seeds 117-119 at 1%/5%/25%)
and then prints the verdict whose rule was written in advance (`docs/PREREGISTRATION.md`,
Amendment M9-e). Nothing here touches the evaluation seeds 0-9.

**How to use it.** Run the cells **top to bottom, one at a time** (click a cell, Shift+Enter).
Use a **CPU** runtime (Runtime > Change runtime type > CPU). Expect about **3-4 hours**; keep the
browser tab open. Progress is saved to your Google Drive after every finished unit, so if Colab
disconnects you can reopen the notebook, redo Steps 1-4 and re-run Step 5: finished work is skipped.
"""),
    md("## Step 1 - look at the machine"),
    code("""
import sys, os, platform
print("Python", sys.version.split()[0], "|", platform.platform())
print("CPU cores available:", os.cpu_count())
import torch
print("PyTorch", torch.__version__, "| CUDA available:", torch.cuda.is_available())
"""),
    md("*What you should see:* a Python version, about 2 CPU cores, a PyTorch version. "
       "'CUDA available: False' is fine."),
    md("## Step 2 - upload the project zip\\nRun the cell, click **Choose files**, pick **`rlcache_colab.zip`**."),
    code("""
from google.colab import files
up = files.upload()
import zipfile, hashlib
name = next(iter(up))
print("uploaded:", name, "| SHA-256:", hashlib.sha256(open(name, "rb").read()).hexdigest())
zipfile.ZipFile(name).extractall("/content/rlcache")
%cd /content/rlcache
!ls
"""),
    md("*What you should see:* a SHA-256 string (send it to me) and a list with `src`, `scripts`, `results`."),
    md("## Step 3 - install packages and connect Google Drive (progress is saved there)"),
    code("""
!pip -q install gymnasium pyyaml scipy pandas matplotlib zstandard pytest
from google.colab import drive
drive.mount("/content/drive")
"""),
    md("*What you should see:* a Google pop-up asking to allow Drive access (this is your own Drive; "
       "it is only used to keep the results file safe) and `Mounted at /content/drive`."),
    md("## Step 4 - put the 20 finished units on Drive (only if not already there) and run the tests"),
    code("""
import os, shutil
d = "/content/drive/MyDrive/rlcache_repair"
os.makedirs(d, exist_ok=True)
dst = d + "/dqn_repair_dev.csv"
if not os.path.exists(dst):
    shutil.copy("results/dqn_repair_dev.csv", dst)
    print("copied the 20 finished units to", dst)
else:
    print("already on Drive (a previous session continued it):", dst)
import csv
print("rows in progress file:", sum(1 for _ in csv.DictReader(open(dst))))
!python -m pytest -q -W ignore tests/
"""),
    md("*What you should see:* `rows in progress file: 240` (more if a previous session continued it) and then "
       "`... passed`. **STOP** if you see `failed` and send me the output."),
    md("""
## Step 5 - run the remaining work (the long step, about 3-4 hours)
This trains the three agents (`dqn`, `dqn_bandit`, and the new `dqn_perkey`) for the missing units and
appends each finished unit to the file on Drive.
"""),
    code("""
!python scripts/run_dqn.py --stage dev --backend torch --procs 2 \\
    --seeds 110 111 112 113 114 115 116 117 118 119 \\
    --variants dqn dqn_bandit dqn_perkey \\
    --out /content/drive/MyDrive/rlcache_repair/dqn_repair_dev.csv \\
    --ckpt /content/dqn_ckpt_repair --tabq-csv nonexistent.csv
"""),
    md("*What you should see:* lines like `seed 117 cap 0.01: +12 rows`, ending with `wrote 120 new rows` "
       "(fewer if you resumed). Then some tables from the old gate report - **ignore those**; the "
       "result that matters is Step 6."),
    md("## Step 6 - the verdict that was fixed in advance"),
    code("""
!python scripts/dqn_repair_report.py --csv /content/drive/MyDrive/rlcache_repair/dqn_repair_dev.csv --out /content/dqn_repair_report.json
"""),
    md("*What you should see:* paired tables per cache size and a final line "
       "`PRE-REGISTERED VERDICT (Amendment M9-e): REPAIRED / PARTIAL / NOT REPAIRED`. "
       "Copy the whole output and send it back."),
    md("## Step 7 - download the results"),
    code("""
!cp /content/drive/MyDrive/rlcache_repair/dqn_repair_dev.csv /content/dqn_repair_dev.csv
!zip -q dqn_repair_results.zip /content/dqn_repair_dev.csv /content/dqn_repair_report.json
from google.colab import files
files.download("dqn_repair_results.zip")
"""),
]


def build_notebook() -> dict:''')
rep('''    (OUT / "M9_dqn_colab.ipynb").write_text(json.dumps(build_notebook(), indent=1), encoding="utf-8")''',
    '''    (OUT / "M9_dqn_colab.ipynb").write_text(json.dumps(build_notebook(), indent=1), encoding="utf-8")
    (OUT / "M9e_repair_colab.ipynb").write_text(json.dumps(build_notebook(REPAIR_CELLS), indent=1), encoding="utf-8")''')
rep('''def build_notebook() -> dict:
    return {"cells": CELLS,''', '''def build_notebook(cells=None) -> dict:
    return {"cells": CELLS if cells is None else cells,''')
rep('''        if extra is not None:
            z.write(extra, "results/tabq_dev.csv")
            n += 1''', '''        if extra is not None:
            z.write(extra, "results/tabq_dev.csv")
            n += 1
        part = ROOT / "results" / "dqn_repair_dev.csv"            # M9-e: the 20 units finished locally
        if part.exists():
            z.write(part, "results/dqn_repair_dev.csv")
            n += 1''')
p.write_text(s, encoding="utf-8")
print("ok")
