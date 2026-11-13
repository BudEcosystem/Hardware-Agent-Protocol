"""Render static SVG through installed librsvg's internal pixbuf path."""
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import gi
gi.require_version('Rsvg', '2.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Rsvg

BASE = Path(__file__).resolve().parent
receipt = json.loads((BASE / 'reading.json').read_bytes())
rendered = []
for row in receipt['diagrams']:
    path = BASE / row['path']; body = path.read_bytes()
    assert hashlib.sha256(body).hexdigest() == row['sha256']
    root = ET.fromstring(body)
    for element in root.iter():
        assert element.tag.rsplit('}', 1)[-1] in {'svg','circle','polygon','path','text'}
        assert all(not key.lower().startswith('on') and not key.endswith('href') for key in element.attrib)
        assert all('url(' not in value.lower() for value in element.attrib.values())
    x,y,width,height = map(float, root.attrib['viewBox'].split())
    assert x == y == 0 and 0 < width < 1000 and 0 < height < 200
    size = (math.ceil(width * 2), math.ceil(height * 2))
    # Rendering viewport only; the retained SVG stays byte-exact.
    render_body = body.replace(b'<svg ', ('<svg width="%d" height="%d" ' % size).encode(), 1)
    handle = Rsvg.Handle.new_from_data(render_body)
    pixbuf = handle.get_pixbuf()
    assert pixbuf is not None and (pixbuf.get_width(), pixbuf.get_height()) == size
    ok, png = pixbuf.save_to_bufferv('png', [], []); assert ok
    output = path.with_suffix('.png')
    with output.open('xb') as stream: stream.write(bytes(png))
    rendered.append(dict(source=row['path'], path=output.relative_to(BASE).as_posix(),
        dimensions=size, bytes=output.stat().st_size, sha256=hashlib.sha256(output.read_bytes()).hexdigest()))
with (BASE / 'rendering02.json').open('x') as stream:
    json.dump(dict(renderer='System librsvg through PyGObject pixbuf', images=rendered,
        sourceScriptsExecuted=False, sourceExternalResourcesAllowed=False), stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(rendered=len(rendered))))
