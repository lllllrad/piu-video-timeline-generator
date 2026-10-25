"""Official UCS catalogue and timing archives, cached outside tracked chart data."""
from io import BytesIO
import http.cookiejar
import json
import os
from pathlib import Path
import re
import ssl
import urllib.error
import urllib.request
import uuid
import zipfile

from piu_timeline.charts import ucs


BASE_URL = 'https://ucs.piugame.com/sample_download'
CATALOG_URL = BASE_URL + '/pdf.php'
from piu_timeline import ROOT
DEFAULT_CACHE = ROOT / '.local/cache/ucs'


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.build-' + uuid.uuid4().hex)
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def index(value):
    value = value.upper()
    if not re.fullmatch(r'CS\d{3,5}', value):
        raise ValueError('UCS index must be a catalogue code such as CS349')
    return value


class Client:
    def __init__(self, cache=DEFAULT_CACHE):
        self.cache = Path(cache)
        context = ssl.create_default_context()
        # Some official hosts omit intermediate certificates. An optional local
        # CA bundle supplements normal hostname and certificate verification.
        ca_file = os.environ.get('PIU_UCS_CA_FILE')
        if ca_file or (self.cache / 'intermediates.pem').is_file():
            context.load_verify_locations(ca_file or self.cache / 'intermediates.pem')
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),
                                                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def download(self, url, limit):
        # Anonymous SSO may first return a malformed callback (404). Retry the
        # original URL with in-memory cookies; never persist session material.
        for attempt in range(2):
            try:
                with self.opener.open(url, timeout=30) as response:
                    content = response.read(limit + 1)
                if len(content) > limit:
                    raise ValueError('Official UCS response exceeds size limit')
                return content
            except urllib.error.HTTPError as error:
                if attempt or error.code != 404:
                    raise

    def catalogue(self, refresh=False):
        path = self.cache / 'catalog.pdf'
        content = path.read_bytes() if path.is_file() and not refresh else self.download(CATALOG_URL, 10_000_000)
        result = parse_catalogue(content)
        if not path.is_file() or refresh:
            atomic_write(path, content)
        return result

    def template(self, code):
        code = index(code)
        path = self.cache / f'{code}.zip'
        url = BASE_URL + '/zip.php?ucs_index=' + code
        content = path.read_bytes() if path.is_file() else self.download(url, 40_000_000)
        document, music = read_archive(content, code)
        if not path.is_file():
            atomic_write(path, content)
        music_path = self.cache / f'{code}.mp3'
        if not music_path.is_file() or music_path.read_bytes() != music:
            atomic_write(music_path, music)
        return document, music_path, url


def read_archive(content, code):
    code = index(code)
    if len(content) > 40_000_000:
        raise ValueError('UCS archive exceeds size limit')
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            def member(suffix, limit):
                matches = [info for info in archive.infolist() if Path(info.filename).name.casefold() == (code+suffix).casefold()]
                if len(matches) != 1 or not 0 < matches[0].file_size <= limit:
                    raise ValueError(f'Expected one bounded {code}{suffix} in UCS archive')
                return archive.read(matches[0])
            text = member('.ucs', 2_000_000).decode('utf-8-sig')
            music = member('.mp3', 32_000_000)
    except (zipfile.BadZipFile, UnicodeError, RuntimeError) as error:
        raise ValueError('Invalid official UCS ZIP response') from error
    document = ucs.parse(text)
    if any(set(row) != {'.'} for section in document.sections for row in section.rows):
        raise ValueError('Official download was expected to contain a blank timing template')
    return document, music


def catalogue_cells(pages):
    """Read PDF cells by column; wrapped rows may continue on the next page."""
    entries, current = [], None
    columns = [(43.3, 'index'), (94.3, 'bpm'), (170.9, 'delay_ms'), (247.4, 'artist'), (349.5, 'title')]
    for page in pages:
        for x, y, text in page:
            text = ' '.join(text.split())
            if not text or y < 40 or text.startswith('UCS SONG LIST') or text in ('UCS', 'CODE', 'BPM', 'Delay(ms)', 'Artist', 'Song'):
                continue
            column = min(columns, key=lambda pair: abs(pair[0]-x))
            if abs(column[0]-x) > 3:
                continue
            field = column[1]
            if field == 'index':
                if not re.fullmatch(r'CS\d{3,5}', text):
                    continue
                current = {'index': text}
                entries.append(current)
            elif current is not None:
                current[field] = ' '.join(filter(None, (current.get(field), text)))
    if not entries or len({entry['index'] for entry in entries}) != len(entries) or any(not entry.get('title') for entry in entries):
        raise ValueError('Incomplete or duplicate official catalogue rows')
    return entries


def parse_catalogue(content):
    if not content.startswith(b'%PDF-'):
        raise ValueError('Official catalogue response is not a PDF')
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(content))
    if not 1 <= len(reader.pages) <= 100:
        raise ValueError('Unexpected UCS catalogue page count')
    pages = []
    for page in reader.pages:
        cells = []
        page.extract_text(visitor_text=lambda text, cm, tm, font, size: cells.append((tm[4], tm[5], text)))
        pages.append(cells)
    from hashlib import sha256
    return {'schema': 1, 'source_url': CATALOG_URL, 'pdf_sha256': sha256(content).hexdigest(), 'songs': catalogue_cells(pages)}
