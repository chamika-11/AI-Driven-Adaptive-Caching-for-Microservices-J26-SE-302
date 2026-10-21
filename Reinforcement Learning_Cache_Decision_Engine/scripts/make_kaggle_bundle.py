"""Build the Kaggle package for Addendum M11-F (finishing the S3-FIFO development run on Kaggle).

    python scripts/make_kaggle_bundle.py
Writes kaggle_bundle/rlcache_kaggle.zip (code + docs + the 15 already-finished trainings in results/dqn_s3_dev.csv)
and kaggle_bundle/M11F_s3_kaggle.ipynb.  Nothing from results.csv is included.
"""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "kaggle_bundle"
INCLUDE_DIRS = ["src", "scripts", "tests", "configs", "docs"]
INCLUDE_FILES = ["pyproject.toml", "requirements-colab.txt"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "data", "scratch", "results", "colab_bundle", "kaggle_bundle"}


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(True)}


CELLS = [
    md("""
# Finishing the S3-FIFO experiment on Kaggle (Addendum M11-F)

This notebook trains the learning agent on a cache that uses the S3-FIFO eviction rule and compares it with simple
rules. 15 of the 30 trainings were already done on your PC and are inside the zip; this notebook only does the rest
(about 15 trainings and the reference policies). Everything is synthetic data. **Accelerator must be None (CPU)** and
**Internet must be ON** (Settings menu).

Run the cells top to bottom (Shift+Enter), or use **Save Version > Save & Run All** and close the tab: it keeps running.
"""),
    md("## Step 1 - machine check"),
    code("""
import os, sys, platform, glob
print("Python", sys.version.split()[0], "|", platform.platform(), "| CPU cores:", os.cpu_count())
print("input files:", glob.glob("/kaggle/input/*"))
"""),
    md("*You should see:* about 4 CPU cores and your dataset folder under `/kaggle/input/...`."),
    md("## Step 2 - unpack the project"),
    code("""
import zipfile, hashlib, glob, os, shutil
zips = glob.glob("/kaggle/input/**/rlcache_kaggle.zip", recursive=True)
if zips:                                              # Kaggle kept the zip as a file
    print("zip:", zips[0], "| SHA-256:", hashlib.sha256(open(zips[0], "rb").read()).hexdigest())
    zipfile.ZipFile(zips[0]).extractall("/kaggle/working/rlcache")
else:                                                 # Kaggle already unpacked the zip into folders
    marker = glob.glob("/kaggle/input/**/scripts/run_s3_dev.py", recursive=True)[0]
    root = os.path.dirname(os.path.dirname(marker))
    print("unpacked dataset found at:", root)
    shutil.copytree(root, "/kaggle/working/rlcache", dirs_exist_ok=True)
%cd /kaggle/working/rlcache
!ls
"""),
    md("## Step 3 - install the few extra packages (needs Internet ON)"),
    code("!pip -q install gymnasium pyyaml scipy pandas matplotlib zstandard pytest"),
    md("## Step 4 - quick self-check (about 1-2 minutes)"),
    code("!python -m pytest -q -W ignore tests/test_s3_arm.py tests/test_eviction.py tests/test_dqn_numpy.py"),
    md("*You should see:* dots and `... passed`. **STOP** if you see `failed` and send me the output."),
    md("## Step 5 - put the 15 finished trainings in the output folder, then run the rest (about 1 hour)"),
    code("""
import shutil, csv
shutil.copy("results/dqn_s3_dev.csv", "/kaggle/working/dqn_s3_dev.csv")
print("rows already done:", sum(1 for _ in csv.DictReader(open("/kaggle/working/dqn_s3_dev.csv"))))
!python scripts/run_s3_dev.py --procs 4 --out /kaggle/working/dqn_s3_dev.csv
"""),
    md("*You should see:* lines like `train seed 125 dqn:main@s3fifo: +1 rows (...)` and `refs seed 120 refs: +82 rows`, "
       "ending with `wrote ... new rows`. If the session stops, run Steps 2, 3 and 5 again: finished work is skipped."),
    md("## Step 6 - the verdict that was fixed in advance"),
    code("!python scripts/s3_dev_report.py --csv /kaggle/working/dqn_s3_dev.csv --out /kaggle/working/dqn_s3_dev_report.json"),
    md("*You should see:* tables and a final line `PRE-REGISTERED VERDICT (Amendment M11-F): SUPPORTED-FRONTIER / SUPPORTED-U / NOT SUPPORTED`. "
       "Copy the whole output and send it to me."),
    md("## Step 7 - get your files\nThe results are in `/kaggle/working/` (`dqn_s3_dev.csv`, `dqn_s3_dev_report.json`). After "
       "Save & Run All, open the notebook's **Output** tab and download both files; put them in the project's `results` folder."),
]


def main():
    OUT.mkdir(exist_ok=True)
    zpath = OUT / "rlcache_kaggle.zip"
    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d in INCLUDE_DIRS:
            for p in sorted((ROOT / d).rglob("*")):
                if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_PARTS) and p.suffix not in (".pyc", ".png"):
                    z.write(p, p.relative_to(ROOT).as_posix())
                    n += 1
        for f in INCLUDE_FILES:
            if (ROOT / f).exists():
                z.write(ROOT / f, f)
                n += 1
        part = ROOT / "results" / "dqn_s3_dev.csv"
        z.write(part, "results/dqn_s3_dev.csv")
        n += 1
    nb = {"cells": CELLS, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                       "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    (OUT / "M11F_s3_kaggle.ipynb").write_text(json.dumps(nb, indent=1), encoding="utf-8")
    print(f"{n} files -> {zpath} ({zpath.stat().st_size/1e6:.2f} MB)")
    print("sha256:", hashlib.sha256(zpath.read_bytes()).hexdigest())


if __name__ == "__main__":
    sys.exit(main())
