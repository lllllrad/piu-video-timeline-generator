"""Display the exact masked reference pixels, region boxes and native anchors."""
from base64 import b64encode
from html import escape
from pathlib import Path

from piu_timeline.play.skins.bank import load_bank


def review_bank(path, output, lane_kind=None):
    path, output = Path(path).resolve(), Path(output)
    bank = load_bank(path)
    cards = []
    for template in bank['templates']:
        if lane_kind is not None and template['lane_kind'] != lane_kind:
            continue
        height, width = template['mask'].shape
        encoded = b64encode((path.parent / template['image']).read_bytes()).decode('ascii')
        ax, ay = template['anchor_pixels']
        overlays, labels = [], []
        for region in template['regions']:
            x0, y0, x1, y1 = region['box']
            name = region['name']
            color = '#ff6688' if name.startswith('connection') else '#38d8ff'
            for a,b,c,d in region.get('comparison_boxes',[region['box']]):
                overlays.append(f'<rect x="{a}" y="{b}" width="{c-a}" height="{d-b}" '
                                f'fill="none" stroke="{color}" stroke-width="0.35"/>')
            labels.append(escape(f'{name}: {region["box"]}; RGB MSE ≤ {region.get("maximum_error", .015)}'))
        overlays.append(f'<path d="M {ax-2} {ay} h 4 M {ax} {ay-2} v 4" '
                        'stroke="#78ff79" stroke-width="0.5"/>')
        heading = escape(f'{template["id"]} · lane kind {template["lane_kind"]} · {template["role"]}')
        cards.append(f'<article><h2>{heading}</h2><svg xmlns="http://www.w3.org/2000/svg" '
                     f'viewBox="0 0 {width} {height}" width="{width*4}" height="{height*4}">'
                     f'<image href="data:image/png;base64,{encoded}" width="{width}" height="{height}"/>'
                     f'{"".join(overlays)}</svg><p>{width} × {height} native pixels; '
                     f'anchor [{ax}, {ay}]</p><ul>{"".join(f"<li>{label}</li>" for label in labels)}</ul></article>')
    if not cards:
        raise ValueError('No skin references match the requested lane kind')
    title = escape(bank['skin'])
    html = ('<!doctype html><html lang="en"><meta charset="utf-8">'
            f'<title>{title}: reference regions</title><style>'
            'body{background:#17191d;color:#eee;font:15px sans-serif;margin:24px}'
            'main{display:flex;flex-wrap:wrap;gap:20px}article{border:1px solid #777;padding:12px;max-width:420px}'
            'h2{font-size:15px;overflow-wrap:anywhere}svg{background:repeating-conic-gradient(#444 0% 25%,#222 0% 50%) 0/12px 12px;image-rendering:pixelated}'
            'li{font:12px monospace}p{max-width:900px}</style>'
            f'<h1>{title}: exact reference regions</h1>'
            '<p>Images show the original PNG alpha mask at 4× native size. Checkerboard pixels are excluded. '
            'Cyan boxes mark selected cap, body or clearance areas; pink marks connections; green marks the anchor. '
            'Only source-supported pixels inside the selected comparison boxes contribute to RGB comparison. '
            'Unmarked context pixels do not supply geometry. '
            'These are reference coordinates; source-frame placements additionally scale with lane spacing.</p>'
            f'<main>{"".join(cards)}</main></html>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html)
    return output
