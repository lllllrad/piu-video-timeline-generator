"""One-command media preparation, analysis, and TypeScript presentation."""
import argparse
import hashlib
import fcntl
import uuid
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import parse_qs, urlparse

from .auto_timeline import ANALYSIS_VERSION, analyze, resolve_source
from .detect import roi_value
from .ocr import configuration
from .storage import relocate_evidence
ROOT = Path(__file__).resolve().parents[2]
LOCAL_DATA = ROOT / ".local/data"
LOCAL_FORMATS = ROOT / ".local/formats"
BUILTIN_FORMATS = ROOT / "formats"


def source_id(source):
    local = Path(source).expanduser()
    if local.is_file():
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", local.stem).strip("-.") or "video"
        digest = hashlib.sha256(str(local.resolve()).encode()).hexdigest()[:8]
        return f"{stem}-{digest}"
    parsed = urlparse(source)
    if parsed.hostname == "youtu.be":
        candidate = parsed.path.strip("/").split("/", 1)[0]
    elif parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        candidate = parse_qs(parsed.query).get("v", [None])[0]
        if candidate is None and parsed.path.startswith(("/live/", "/shorts/", "/embed/")):
            candidate = parsed.path.split("/", 3)[2]
    else:
        candidate = source if re.fullmatch(r"[A-Za-z0-9_-]{11}", source) else None
    if not candidate or not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        raise ValueError("Could not determine a stable video ID from the source")
    return candidate


def formatter(name):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name) or name in {".", ".."}:
        raise ValueError("Format name may contain letters, numbers, dot, underscore, and hyphen")
    local = LOCAL_FORMATS / name / "index.ts"
    built_in = BUILTIN_FORMATS / name / "index.ts"
    if local.parent.exists():
        if not local.is_file():
            raise ValueError(f"Local format {name!r} is missing its entry point: {local}")
        return local
    if built_in.is_file():
        return built_in
    raise ValueError(f"Unknown format {name!r}; create {local}")


def run_formatter(script, analysis_file):
    result = subprocess.run(["node", str(script), str(analysis_file)], check=True, capture_output=True, text=True)
    if not result.stdout.endswith("\n"):
        raise ValueError("Formatter output must end with a newline")
    return result.stdout


def fetch(source):
    local = Path(source).expanduser()
    if local.is_file():
        raise ValueError("fetch accepts a YouTube URL or video ID, not a local file")
    identifier = source_id(source)
    raw = LOCAL_DATA / identifier / "raw"
    video, _ = resolve_source(source, raw)
    print(video)
    return video


def import_studio(source, video_path):
    identifier = source_id(source)
    video = Path(video_path).expanduser().resolve()
    if not video.is_file():
        raise ValueError(f"Video not found: {video}")
    if video.suffix.lower() not in {".mkv", ".mp4", ".webm", ".mov"}:
        raise ValueError("Studio export must be an MKV, MP4, WebM, or MOV video")
    raw = LOCAL_DATA / identifier / "raw"
    existing = [path for path in raw.iterdir()
                if path.is_file() and path.suffix.lower() in {".mkv", ".mp4", ".webm", ".mov"}] if raw.is_dir() else []
    destination = raw / f"{identifier}{video.suffix.lower()}"
    if video == destination:
        print(destination)
        return destination
    if existing or destination.exists():
        raise ValueError(f"A cached video already exists in {raw}")
    raw.mkdir(parents=True, exist_ok=True)
    shutil.move(video, destination)
    print(destination)
    return destination



def run(source, format_name="default", game_roi=None):
    directory = LOCAL_DATA / source_id(source)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".auto.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(f"Another auto run is processing {directory.name}") from error
        return _run(source, format_name, game_roi)


def _run(source, format_name="default", game_roi=None):
    identifier = source_id(source)
    directory = LOCAL_DATA / identifier
    raw = directory / "raw"
    analysis_dir = directory / "analysis"
    analysis_file = analysis_dir / "analysis.json"
    output = directory / "output" / f"{format_name}.txt"
    script = formatter(format_name)
    document = json.loads(analysis_file.read_text(encoding="utf-8")) if analysis_file.is_file() else None
    stale = document is not None and document.get("analysis_version") != ANALYSIS_VERSION
    if document is not None:
        stale |= game_roi is not None and list(game_roi) != document.get("game_roi")
        stale |= document.get("ocr_configuration", configuration()) != configuration()
        media = document.get("media")
        if media:
            cached_source = Path(media["path"])
            stale |= not cached_source.is_file()
            if cached_source.is_file():
                stat = cached_source.stat()
                stale |= (stat.st_size, stat.st_mtime_ns) != (media["size_bytes"], media["mtime_ns"])
    if document is None or stale:
        if analysis_dir.exists() and not stale:
            raise ValueError(f"Incomplete analysis exists: {analysis_dir}")
        raw.mkdir(parents=True, exist_ok=True)
        video, provenance = resolve_source(source, raw)
        if provenance.get("kind") == "local":
            link = raw / video.name
            if not link.exists():
                link.symlink_to(video.resolve())
            video = link
        target = directory / f"analysis.build-{uuid.uuid4().hex[:12]}"
        effective_roi = game_roi or (tuple(document["game_roi"]) if document and document.get("game_roi") else None)
        # Reuse source-verified acquisition; acquire missing scene/identity
        # samples while preserving decoded boundaries and result evidence.
        reusable = (document and document.get("analysis_version") in {5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29}
                    and document.get("ocr_configuration") == configuration()
                    and document.get("game_roi") == list(effective_roi or [])
                    and document.get("media", {}).get("size_bytes") == video.stat().st_size
                    and document.get("media", {}).get("mtime_ns") == video.stat().st_mtime_ns
                    and (analysis_dir / "profiles.json").is_file()
                    and (analysis_dir / "candidates.json").is_file())
        if reusable:
            analyze(video, target, effective_roi, provenance, retained=analysis_dir)
        else:
            analyze(video, target, effective_roi, provenance)
        relocate_evidence(target, analysis_dir)
        backup = directory / f"analysis.previous-{uuid.uuid4().hex[:12]}"
        if analysis_dir.exists():
            analysis_dir.rename(backup)
        try:
            target.rename(analysis_dir)
        except OSError:
            if backup.exists():
                backup.rename(analysis_dir)
            raise
        if backup.exists():
            relocate_evidence(backup, backup, source=analysis_dir)
        document = json.loads(analysis_file.read_text(encoding="utf-8"))
    if document.get("method") != "automatic_hud_ocr":
        raise ValueError("Saved analysis is not an automatic HUD analysis")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    text = run_formatter(script, analysis_file)
    output.write_text(text, encoding="utf-8")
    print(text, end="")
    print(f"Saved: {output}")
    return output


def auto_main(arguments):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Local video, YouTube URL, or 11-character video ID")
    parser.add_argument("format", nargs="?", default="default")
    parser.add_argument("--game-roi", type=roi_value, help="x,y,width,height of the game screen")
    args = parser.parse_args(arguments)
    try:
        run(args.source, args.format, args.game_roi)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.error(str(error))
    except subprocess.CalledProcessError as error:
        parser.error(f"External tool failed: {error.stderr or error}")


def fetch_main(arguments):
    parser = argparse.ArgumentParser(description="Download or reuse a YouTube video in .local/data.")
    parser.add_argument("source", help="YouTube URL or 11-character video ID")
    args = parser.parse_args(arguments)
    try:
        fetch(args.source)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    except subprocess.CalledProcessError as error:
        parser.error(f"Download failed: {error.stderr or error}")


def import_studio_main(arguments):
    parser = argparse.ArgumentParser(description="Move a YouTube Studio export into the cache used by auto.")
    parser.add_argument("source", help="YouTube URL or 11-character video ID")
    parser.add_argument("video", help="Path to the downloaded Studio export")
    args = parser.parse_args(arguments)
    try:
        import_studio(args.source, args.video)
    except (ValueError, OSError) as error:
        parser.error(str(error))


def main():
    import sys
    commands = {"auto": auto_main, "fetch": fetch_main, "import-studio": import_studio_main}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        raise SystemExit("usage: workflow.py {auto|fetch|import-studio} ...")
    commands[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
