"""Discover prepared plays and lazily open independent source/segment contexts."""
import json
from pathlib import Path
from threading import Lock
from time import monotonic

from piu_timeline.review.index import ReportIndex, build, signature
from piu_timeline.review.store import ReviewStore


class ReviewLibrary:
    def __init__(self, root, window_root=None):
        self.root = Path(root).resolve()
        self.window_root = Path(window_root).resolve() if window_root is not None else None
        self.lock = Lock()
        self.cache = {}
        self.catalog_until = 0
        self.catalog_cache = []
        self.default_source = None
        self.default_segment = None

    def catalog(self):
        if monotonic() < self.catalog_until:
            return self.catalog_cache
        sources = []
        directories = sorted(self.root.iterdir()) if self.root.is_dir() else []
        if self.window_root is not None:
            primary_names = {directory.name for directory in directories}
            directories.extend(directory for directory in sorted(self.window_root.glob('play-window-*'))
                               if directory.name not in primary_names)
        for directory in directories:
            if not directory.is_dir() or directory.is_symlink():
                continue
            analysis = directory / 'analysis/analysis.json'
            document = {}
            try:
                if analysis.stat().st_size <= 2 * 1024 * 1024:
                    document = json.loads(analysis.read_text())
            except (OSError, ValueError):
                pass
            if not isinstance(document, dict):
                document = {}
            segments = []
            for play in sorted((directory / 'play').glob('segment-*')):
                prepared = play / 'report-data.json'
                if not prepared.is_file() or not prepared.resolve().is_relative_to(directory.resolve()):
                    continue
                try:
                    number = int(play.name.removeprefix('segment-'))
                except ValueError:
                    continue
                if number < 1:
                    continue
                original = document.get('segments', [])
                detail = original[number - 1] if number <= len(original) else {}
                segments.append({'number': number, 'song': detail.get('song'), 'chart': detail.get('chart')})
            if segments:
                sources.append({'id': directory.name, 'segments': segments})
        self.catalog_cache = sources
        self.catalog_until = monotonic() + 2
        return sources

    def open(self, source=None, segment=None):
        source = source or self.default_source
        catalog = {item['id']: item for item in self.catalog()}
        if source not in catalog:
            raise FileNotFoundError('No prepared analysis for this video')
        segments = catalog[source]['segments']
        number = int(segment) if segment is not None else (self.default_segment if source == self.default_source else segments[0]['number'])
        if number not in {item['number'] for item in segments}:
            raise FileNotFoundError('No prepared analysis for this segment')
        source_directory = self.root / source
        if not source_directory.is_dir() and self.window_root is not None:
            source_directory = self.window_root / source
        directory = source_directory / 'play' / f'segment-{number:03}'
        prepared = directory / 'report-data.json'
        stamp = signature(prepared)
        key = (source, number)
        with self.lock:
            saved = self.cache.get(key)
            if saved is None or saved[0] != stamp:
                index = ReportIndex(build(prepared, directory / 'review/index.sqlite'))
                metadata = {**index.metadata(), 'source_id': source, 'ucs_draft': (directory/'chart.ucs').is_file()}
                store = ReviewStore(directory / 'review/intervals', metadata)
                saved = (stamp, (index, store, metadata, Path(metadata['media']['path']), directory))
                if len(self.cache) >= 8:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[key] = saved
            return saved[1]
