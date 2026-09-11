"""Build the Aptech submission zip and Word-compatible ReadMe.doc.

Usage (from the repo root):

    python scripts/make_submission.py

Writes ``dist/WeatherPredict-submission.zip`` and ``ReadMe.doc``.
The zip excludes virtualenvs, git metadata, caches, logs and local backups.
"""
from __future__ import annotations

import html
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".cursor",
    "backups",
    "logs",
    "dist",
    "htmlcov",
    "node_modules",
}
SKIP_SUFFIXES = {".pyc", ".pyo", ".log"}
SKIP_NAMES = {".env", "debug-a1cb32.log", "Thumbs.db"}


ASSUMPTIONS = [
    "MongoDB is available at mongodb://localhost:27017.",
    "Climate history for demos is synthetic (python -m weatherpredict.seed --with-data), not a live satellite or agency feed. Satellite support is a metadata catalogue — no rasters are read.",
    "Hadoop/HDFS/MapReduce, Tableau and Impala are out of scope for the local demo. Upgrade paths are in README.md and docs/ARCHITECTURE.md.",
    "Demo passwords are for local evaluation only.",
    "Real-time ingestion is a manually triggered simulator, merged with batch history in one view.",
    "No PII is stored beyond username, email and role. TLS is terminated at a reverse proxy in production.",
    "99% uptime is an operational SLO of the host. python -m weatherpredict.health is the in-app probe.",
    "The app is single-worker. Streamlit session state lives in one process.",
    "Jupyter, RStudio and a specific IDE are suggested tooling in the brief, not deliverables.",
]


def _readme_doc() -> str:
    items = "".join(f"<li>{html.escape(item)}</li>" for item in ASSUMPTIONS)
    return f"""<html xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:w="urn:schemas-microsoft-com:office:word">
<head>
<meta charset="utf-8"/>
<title>WeatherPredict — ReadMe</title>
</head>
<body>
<h1>WeatherPredict</h1>
<p>Climate-data intelligence platform for EarthScape Climate Agency.</p>
<p>Generated {date.today().isoformat()}.</p>
<h2>How to run</h2>
<ol>
<li>Install Python 3.11+ and MongoDB Community on localhost:27017.</li>
<li>Create a venv, then <code>pip install -r requirements.txt</code>.</li>
<li>Copy <code>.env.example</code> to <code>.env</code>.</li>
<li>Run <code>python -m weatherpredict.seed --with-data --years 2 --train</code>.</li>
<li>Run <code>streamlit run app.py</code> and open http://127.0.0.1:8501/.</li>
</ol>
<p>Demo accounts: admin / AdminPass123! (Administrator, all regions);
analyst / AnalystPass123! (Analyst, pacific_nw only).</p>
<h2>Assumptions</h2>
<ol>{items}</ol>
<p>Full documentation lives in README.md and the docs/ folder.</p>
</body>
</html>
"""


def _should_skip(path: Path) -> bool:
    if path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES:
        return True
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def main() -> int:
    DIST.mkdir(exist_ok=True)
    readme = ROOT / "ReadMe.doc"
    readme.write_text(_readme_doc(), encoding="utf-8")

    zip_path = DIST / "WeatherPredict-submission.zip"
    count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in ROOT.rglob("*"):
            if not path.is_file() or _should_skip(path.relative_to(ROOT)):
                continue
            zf.write(path, path.relative_to(ROOT).as_posix())
            count += 1
    print(f"Wrote {readme} and {zip_path} ({count} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
