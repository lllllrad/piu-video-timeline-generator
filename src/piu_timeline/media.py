"""YouTube download and local media inspection helpers."""
import argparse
from collections import deque
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse

def resolve_url(source):
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", source):
        return f"https://www.youtube.com/watch?v={source}"
    parsed = urlparse(source)
    if parsed.scheme not in {"https", "http"} or parsed.hostname not in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"
    }:
        raise ValueError("Expected a YouTube URL or 11-character video ID")
    return source


def fetch_command(source, output_root, concurrent_fragments=4):
    if isinstance(concurrent_fragments, bool) or not isinstance(concurrent_fragments, int) or not 1 <= concurrent_fragments <= 16:
        raise ValueError("concurrent_fragments must be an integer between 1 and 16")
    # Ignore machine-wide settings and cookies; preserve the original timebase.
    destination = Path(output_root)
    command = [
        "yt-dlp", "--ignore-config", "--no-playlist", "--no-overwrites",
        "--match-filters", "!is_live", "--write-info-json",
        "--js-runtimes", "node", "--paths", str(destination), "--output", "%(id)s.%(ext)s",
        "--format", "bv*+ba/b", "--merge-output-format", "mkv",
        "--concurrent-fragments", str(concurrent_fragments), "--progress-delta", "5",
        "--progress", "--newline", "--no-quiet",
    ]
    return command + ["--", resolve_url(source)]


def run_download(command):
    """Stream downloader logs while retaining only completed-file markers."""
    markers = []
    recent = deque(maxlen=20)
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1) as process:
        for line in process.stdout:
            if line.startswith("PIU_FILE:"):
                markers.append(line)
            else:
                print(line, end="", file=sys.stderr, flush=True)
                recent.append(line)
        returncode = process.wait()
    if returncode:
        raise subprocess.CalledProcessError(returncode, command, stderr="".join(recent))
    return "".join(markers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        path = args.path.expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Video not found: {path}")
        command = ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
        subprocess.run(command, check=True)
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error


def resolve_source(source, raw_dir=None):
    local = Path(source).expanduser()
    if local.is_file():
        return local.resolve(), {"kind": "local", "network_used": False}
    url = resolve_url(source)
    if raw_dir is None:
        raise ValueError("YouTube sources require a local raw directory")
    destination = Path(raw_dir)
    destination.mkdir(parents=True, exist_ok=True)
    existing = [path.resolve() for path in destination.iterdir()
                if path.is_file() and path.suffix.lower() in {".mkv", ".mp4", ".webm", ".mov"}]
    if len(existing) == 1:
        return existing[0], {"kind": "cached_youtube", "url": url, "network_used": False}
    if len(existing) > 1:
        raise ValueError(f"Multiple videos found in {destination}")
    command = fetch_command(source, destination)
    command[-2:-2] = ["--print", "after_move:PIU_FILE:%(filepath)s"]
    output = run_download(command)
    paths = [Path(line.removeprefix("PIU_FILE:")).resolve() for line in output.splitlines()
             if line.startswith("PIU_FILE:")]
    if len(paths) != 1 or not paths[0].is_file() or not paths[0].is_relative_to(destination):
        raise ValueError("Download did not return exactly one completed video")
    return paths[0], {"kind": "youtube_download", "url": url, "network_used": True,
                      "timing_policy": "full untrimmed download; no local offset inferred"}


if __name__ == "__main__":
    main()
