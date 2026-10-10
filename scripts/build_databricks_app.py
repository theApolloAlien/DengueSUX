"""Assemble a self-contained Databricks Apps source folder (small requirements, only the modules the web app imports).

Usage: python scripts/build_databricks_app.py OUT_DIR [--web-from DIR]
  --web-from  folder holding the pipeline's web JSON (default: output/web in this repo). Pass a copy downloaded
              from the Databricks Volume to serve exactly what the Databricks pipeline wrote.
Then: databricks workspace import-dir OUT_DIR /Workspace/Users/<you>/denguesux_app --overwrite
      databricks apps deploy denguesux --source-code-path /Workspace/Users/<you>/denguesux_app
"""
import argparse
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULES = ["__init__.py", "notices.py", "growth.py", "runtime.py"]  # all the app imports at request time

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--web-from", default=str(REPO / "output/web"))
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "denguesux").mkdir(parents=True)
    (out / "output").mkdir()
    for name in ("app.py", "DATA_REPORT.md", "MODEL_REPORT.md"):
        shutil.copy2(REPO / name, out / name)
    for name in ("app.yaml", "requirements.txt"):
        shutil.copy2(REPO / "databricks_app" / name, out / name)
    shutil.copytree(REPO / "app", out / "app")
    for m in MODULES:
        shutil.copy2(REPO / "denguesux" / m, out / "denguesux" / m)
    shutil.copytree(args.web_from, out / "output/web")
    shutil.copy2(REPO / "output/denguesux.html", out / "output/denguesux.html")
    files = [p for p in out.rglob("*") if p.is_file()]
    print(f"Built {out}: {len(files)} files, {sum(p.stat().st_size for p in files) / 1e6:.1f} MB")

if __name__ == "__main__":
    main()
