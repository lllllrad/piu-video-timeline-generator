"""Regenerate every cached source locally; preserve originals and log each run."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--sources", nargs="+", help="Optional cached source IDs, in processing order")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8:
        parser.error("--jobs must be between 1 and 8")
    sources = sorted(path for path in (ROOT / ".local/data").iterdir() if (path / "raw").is_dir())
    if args.sources:
        indexed = {path.name: path for path in sources}
        if any(name not in indexed for name in args.sources):
            parser.error("Every --sources value must name an existing cached source")
        sources = [indexed[name] for name in dict.fromkeys(args.sources)]
    destination = ROOT / ".local/runs" / f"regeneration-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    destination.mkdir(parents=True)

    def run(directory):
        files = [p for p in (directory / "raw").iterdir() if p.is_file() and p.suffix.lower() in {".mp4", ".mkv", ".mov", ".webm"}]
        start = time.monotonic()
        if len(files) != 1:
            message = "Expected exactly one completed local recording; refusing any download"
            (destination / f"{directory.name}.log").write_text(message + "\n")
            return {"source": directory.name, "exit_code": 2, "seconds": 0,
                    "source_unchanged": True, "error": message}
        before = {str(p): [p.stat().st_size, p.stat().st_mtime_ns] for p in files}
        source = directory.name if re.fullmatch(r"[A-Za-z0-9_-]{11}", directory.name) else str(files[0].resolve())
        with (destination / f"{directory.name}.log").open("w") as log:
            result = subprocess.run(["just", "auto", source], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        after = {str(p): [p.stat().st_size, p.stat().st_mtime_ns] for p in files}
        return {"source": directory.name, "exit_code": result.returncode,
                "seconds": round(time.monotonic() - start, 1), "source_unchanged": before == after,
                "source_files": before, "output": str(directory / "output/default.txt")}
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run, source): source for source in sources}
        for future in as_completed(futures):
            try:
                item = future.result()
            except Exception as error:
                source = futures[future]
                message = f"{type(error).__name__}: {error}"
                with (destination / f"{source.name}.log").open("a", encoding="utf-8") as log:
                    log.write(message + "\n")
                item = {"source": source.name, "exit_code": 1, "seconds": None,
                        "source_unchanged": None, "error": message}
            results.append(item)
            (destination / "report.json").write_text(json.dumps(results, indent=2) + "\n")
            print(f"{len(results)}/{len(sources)} {item['source']}: exit={item['exit_code']} {item['seconds']}s", flush=True)
    print(destination, flush=True)
    if any(r["exit_code"] or not r["source_unchanged"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
