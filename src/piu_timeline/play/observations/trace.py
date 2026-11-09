"""Bounded-memory views of retained JSONL observations, preserving every field."""
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
import json


@contextmanager
def stream_frames(path, expected_count=None):
    """Validate completeness when the sequential consumer exhausts its input."""
    with path.open() as source:
        def records():
            count = 0
            for line in source:
                count += 1
                yield json.loads(line)
            if expected_count is not None and count != expected_count:
                raise ValueError('Native observation frame counts differ')
        yield records()


class Frame(Mapping):
    """A frame identity whose nested observations are loaded only when requested."""
    def __init__(self, trace, offset, size, record):
        self.trace, self.offset, self.size = trace, offset, size
        self.scalars = {k:v for k,v in record.items() if not isinstance(v, (dict, list))}
        self.keys_ = tuple(record)

    def __len__(self):
        return len(self.keys_)

    def __iter__(self):
        return iter(self.keys_)

    def __getitem__(self, key):
        if key in self.scalars:
            return self.scalars[key]
        if key not in self.keys_:
            raise KeyError(key)
        return self.trace.load(self)[key]


class FrameTrace(Sequence):
    """Replay/random access with at most one decoded frame retained by the reader.

    Consumers must treat observations as immutable. The source stays open for
    the context lifetime; no new media decoding or observation cache is created.
    """
    def __init__(self, path, expected_count=None):
        self.path, self.expected_count = path, expected_count
        self.frames = []
        self.cached_offset, self.cached_record = None, None

    def __enter__(self):
        self.source = self.path.open('rb')
        try:
            while True:
                offset = self.source.tell()
                line = self.source.readline()
                if not line:
                    break
                self.frames.append(Frame(self, offset, len(line), json.loads(line)))
            if self.expected_count is not None and len(self.frames) != self.expected_count:
                raise ValueError('Native observation frame counts differ')
        except BaseException:
            self.source.close()
            raise
        return self

    def load(self, frame):
        if self.source.closed:
            raise ValueError('Native observation trace is closed')
        if self.cached_offset != frame.offset:
            self.source.seek(frame.offset)
            record = json.loads(self.source.read(frame.size))
            self.cached_offset, self.cached_record = frame.offset, record
        return self.cached_record

    def __exit__(self, *error):
        self.cached_record = None
        self.source.close()

    def __len__(self):
        return len(self.frames)

    def __getitem__(self, index):
        return self.frames[index]
