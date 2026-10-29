"""Import official bilingual song names into the separate chart identity registry."""
import fcntl
from hashlib import sha256
import json
from pathlib import Path

from piu_timeline.charts.official import Client, atomic_write, write_json

URL='https://xx.piugame.com/piu.xx/intro/pdf/PumpItUp_xx_FullSongList.pdf'


def cells(pages):
    """Read the documented bilingual table; headings cannot continue a song row."""
    rows=[]
    for page,items in enumerate(pages,1):
        current=None
        for x,y,text in items:
            text=' '.join(text.split())
            if text in ('NORMAL','FULL','SHORT','REMIX'):
                current={'page':page,'type':text,'y':y,'localized_title':[],'title':[]}
                rows.append(current)
            elif current and abs(y-current['y'])<=4:
                if 170<=x<275:current['localized_title'].append(text)
                elif 345<=x<460:current['title'].append(text)
    if not rows:raise ValueError('Official bilingual catalogue has no song rows')
    for row in rows:
        row.pop('y')
        for field in ('localized_title','title'):
            row[field]=' '.join(row[field])
            if not row[field]:raise ValueError('Incomplete bilingual song row')
    return rows


def refresh(repository,client=None,*,redownload=False):
    from pypdf import PdfReader
    from piu_timeline.derived import call
    repository=Path(repository);provider=client or Client()
    path=provider.cache/'official-localized-songs.pdf'
    if redownload or not path.is_file():atomic_write(path,provider.download(URL,10_000_000))
    content=path.read_bytes()
    if not content.startswith(b'%PDF-'):raise ValueError('Official bilingual response is not a PDF')
    document=PdfReader(path)
    if not 1<=len(document.pages)<=100:raise ValueError('Unexpected bilingual catalogue page count')
    pages=[]
    for page in document.pages:
        items=[]
        page.extract_text(visitor_text=lambda text,cm,tm,font,size:items.append((tm[4],tm[5],text))if text.strip()else None)
        pages.append(items)
    rows=cells(pages)
    with (repository/'.chart-data.lock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        catalogue=json.loads((repository/'catalog.json').read_text())
        aliases=json.loads((repository/'aliases.json').read_text())
        result=call('localized.associate',catalogue['songs'],rows,aliases,{'url':URL,'sha256':sha256(content).hexdigest()})
        write_json(repository/'aliases.json',result['aliases'])
    report={k:v for k,v in result.items()if k!='aliases'}
    report.update(source_url=URL,pdf_sha256=sha256(content).hexdigest(),rows=len(rows))
    write_json(provider.cache/'localized-alias-import.json',report)
    return report


def prepare(repository):
    """Only preparation may fetch names; ordinary identity lookup stays read-only."""
    aliases=json.loads((Path(repository)/'aliases.json').read_text())
    if any(v.get('basis')=='official_localized_catalogue'for v in aliases.values()):return None
    return refresh(repository)
