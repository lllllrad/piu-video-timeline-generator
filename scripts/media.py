"""Input preparation only; timeline detection is intentionally not implemented yet."""
import argparse
import json
from pathlib import Path
import subprocess
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def resolve_url(source):
    seeds = json.loads((ROOT / "data/seeds.json").read_text())["videos"]
    for seed in seeds:
        if source == seed["id"]:
            return seed["url"]
    parsed = urlparse(source)
    if parsed.scheme not in {"https", "http"} or parsed.hostname not in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"
    }:
        raise ValueError("Expected a YouTube URL or an ID listed in data/seeds.json")
    return source


def fetch_command(source, metadata_only=False, comments=False):
    # Ignore machine-wide settings and cookies; preserve the original timebase.
    command = [
        "yt-dlp", "--ignore-config", "--no-playlist", "--no-overwrites",
        "--match-filters", "!is_live", "--write-info-json",
        "--paths", str(ROOT / ("data/labels" if comments else "data/raw")),
        "--output", "%(id)s/%(id)s.%(ext)s",
    ]
    if comments:
        command += ["--skip-download", "--write-comments"]
    elif metadata_only:
        command += ["--skip-download"]
    else:
        command += ["--format", "bv*+ba/b", "--merge-output-format", "mkv"]
    return command + ["--", resolve_url(source)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    fetch = commands.add_parser("fetch")
    fetch.add_argument("source")
    fetch.add_argument("--metadata-only", action="store_true")
    fetch.add_argument("--comments", action="store_true", help="Fetch reference comments separately, without video")
    probe = commands.add_parser("probe")
    probe.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "fetch":
            command = fetch_command(args.source, args.metadata_only, args.comments)
        else:
            path = args.path.expanduser().resolve()
            if not path.is_file():
                raise ValueError(f"Video not found: {path}")
            command = ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
        subprocess.run(command, check=True)
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error


if __name__ == "__main__":
    main()
