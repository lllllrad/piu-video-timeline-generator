"""Loopback-only evidence editor with bounded queries and original-media Range delivery."""
import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlparse

from piu_timeline import ROOT
from piu_timeline.review.index import build, ReportIndex
from piu_timeline.review.store import Conflict, ReviewStore
from piu_timeline.workflow import LOCAL_DATA, source_id


def bounded_detail(value, depth=0):
    """Keep inspection responses bounded; original artifacts remain downloadable."""
    if depth > 5:
        return {'omitted': 'Nested evidence retained in source artifact'}
    if isinstance(value, list):
        rows = [bounded_detail(v, depth + 1) for v in value[:30]]
        return {'items': rows, 'total': len(value), 'truncated': len(value) > 30}
    if isinstance(value, dict):
        keys = list(value)[:60]
        return {k: bounded_detail(value[k], depth + 1) for k in keys}
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, int) and abs(value) > 9007199254740991:
        return str(value)
    return value


def handler_for(index, store, assets, segment):
    token = secrets.token_urlsafe(32)
    metadata = index.metadata()
    media = Path(metadata['media']['path'])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def json(self, value, status=200):
            body = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def file(self, path, content_type=None):
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            requested = self.headers.get('Range')
            if requested:
                try:
                    if not requested.startswith('bytes=') or ',' in requested:
                        raise ValueError()
                    low, high = requested[6:].split('-', 1)
                    start = int(low) if low else max(0, size - int(high))
                    end = min(size - 1, int(high)) if low and high else size - 1
                    if start < 0 or start >= size or end < start:
                        raise ValueError()
                    status = 206
                except ValueError:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
            self.send_response(status)
            self.send_header('Content-Type', content_type or mimetypes.guess_type(path)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(max(0, end - start + 1)))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if status == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if self.command == 'HEAD':
                return
            with path.open('rb') as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    block = stream.read(min(65536, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)

        def do_HEAD(self):
            self.do_GET()

        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.valid_host():
                return self.json({'error':'Use the loopback editor URL'},403)
            try:
                self.read_route()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Conflict as error:
                self.json({'error':str(error)},409)
            except (KeyError, FileNotFoundError):
                self.json({'error': 'Resource not found'}, 404)
            except (ValueError, TypeError) as error:
                self.json({'error': str(error)}, 400)

        def read_route(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            def arg(key, default=None):
                return query.get(key, [default])[0]
            if parsed.path=='/' and (arg('source',store.metadata['source_id'])!=store.metadata['source_id'] or int(arg('segment',metadata.get('segment_number',1)))!=metadata.get('segment_number',1)):
                raise ValueError('This server is reviewing another play; start the editor for the requested source and segment')
            if parsed.path == '/api/meta':
                self.json({**metadata, 'source_id': store.metadata['source_id'], 'write_token': token})
            elif parsed.path == '/api/window':
                start, end = float(arg('start')), float(arg('end'))
                if not all(math.isfinite(v) for v in (start, end)) or not start < end or end - start > 120:
                    raise ValueError('Query a finite interval of at most 120 seconds')
                self.json(index.window(arg('kind'), start, end, int(arg('offset', 0)), int(arg('limit', 200))))
            elif parsed.path == '/api/frame':
                seconds=float(arg('time'))
                if not math.isfinite(seconds):raise ValueError('Invalid frame time')
                self.json(index.frame_at(seconds))
            elif parsed.path == '/api/detail':
                self.json(bounded_detail(index.detail(arg('id'))))
            elif parsed.path == '/api/reviews':
                self.json(store.list())
            elif parsed.path == '/api/review':
                self.json(store.get(arg('id')))
            elif parsed.path == '/media':
                stat = media.stat()
                if stat.st_size != metadata['media']['size_bytes'] or str(stat.st_mtime_ns) != metadata['media']['mtime_ns']:
                    raise Conflict('Original recording changed')
                self.file(media)
            elif parsed.path == '/artifact':
                relative = arg('path', '')
                target = (segment / relative).resolve()
                if not relative or not target.is_relative_to(segment.resolve()) or target.suffix not in ('.json', '.jsonl', '.png', '.npz'):
                    raise ValueError('Invalid evidence artifact')
                self.file(target)
            else:
                relative = parsed.path.lstrip('/') or 'index.html'
                path = (assets / relative).resolve()
                if not path.is_relative_to(assets.resolve()):
                    raise ValueError('Invalid asset path')
                self.file(path)

        def do_PUT(self):
            if not self.valid_host():
                return self.json({'error':'Use the loopback editor URL'},403)
            try:
                if self.headers.get('X-Review-Token') != token:
                    return self.json({'error': 'Reload the editor before saving'}, HTTPStatus.FORBIDDEN)
                parsed = urlparse(self.path)
                if parsed.path != '/api/review':
                    return self.json({'error': 'Unknown write route'}, 404)
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4 * 1024 * 1024:
                    raise ValueError('Review request must be at most 4 MiB')
                request = json.loads(self.rfile.read(length))
                identity = parse_qs(parsed.query)['id'][0]
                self.json(store.save(identity, request['document'], request['base_revision']))
            except Conflict as error:
                self.json({'error': str(error)}, 409)
            except (ValueError, KeyError, TypeError) as error:
                self.json({'error': str(error)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--segment', type=int, default=1)
    parser.add_argument('--port', type=int, default=4180)
    args = parser.parse_args()
    if args.segment < 1 or not 0 <= args.port <= 65535:
        parser.error('Invalid segment or port')
    directory = LOCAL_DATA / source_id(args.source) / 'play' / f'segment-{args.segment:03}'
    prepared = directory / 'report-data.json'
    assets = ROOT / '.local/editor/app'
    if not (assets / 'index.html').is_file():
        parser.error('Build the shared editor first: just editor-build')
    print('Indexing prepared evidence (streaming; source media is never changed)...', flush=True)
    index = ReportIndex(build(prepared, directory / 'review/index.sqlite'))
    metadata = {**index.metadata(), 'source_id': source_id(args.source)}
    store = ReviewStore(directory / 'review/intervals', metadata)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(index, store, assets, directory))
    print(f'Play review: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
