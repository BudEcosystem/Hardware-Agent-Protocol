#!/usr/bin/env python3
"""Render static source figures for review; acquired scripts are never executed."""
from pathlib import Path
from PIL import Image,ImageDraw
import json,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2];base=ROOT/'research/wot-architecture';(base/'renders').mkdir(exist_ok=True)
records=[]
for f in json.loads((base/'metadata/figure-inventory.json').read_text()):
 for i,src in enumerate(f['images'],1):
  raw=ROOT/src['raw_path'];dst=base/'renders'/f'{f["number"]:02d}-{i}.png'
  if raw.suffix=='.svg':
   b=raw.read_bytes();root=ET.fromstring(b)
   for el in root.iter():
    assert el.tag.split('}')[-1].lower()!='script'
    for key,value in el.attrib.items():
     key=key.split('}')[-1].lower();assert not key.startswith('on')
     if key in ('href','src'):assert value.startswith(('#','data:')) or (el.tag.split('}')[-1]=='a' and value=='https://desk.draw.io/support/solutions/articles/16000042487')
   import ctypes,ctypes.util
   cairo=ctypes.CDLL(ctypes.util.find_library('cairo'));rsvg=ctypes.CDLL(ctypes.util.find_library('rsvg-2'));gobject=ctypes.CDLL(ctypes.util.find_library('gobject-2.0'))
   cairo.cairo_image_surface_create.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int];cairo.cairo_image_surface_create.restype=ctypes.c_void_p
   cairo.cairo_create.argtypes=[ctypes.c_void_p];cairo.cairo_create.restype=ctypes.c_void_p
   for name in ['cairo_paint','cairo_destroy','cairo_surface_destroy']:getattr(cairo,name).argtypes=[ctypes.c_void_p]
   cairo.cairo_scale.argtypes=[ctypes.c_void_p,ctypes.c_double,ctypes.c_double]
   cairo.cairo_set_source_rgb.argtypes=[ctypes.c_void_p,ctypes.c_double,ctypes.c_double,ctypes.c_double]
   cairo.cairo_surface_write_to_png.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
   rsvg.rsvg_handle_new_from_file.argtypes=[ctypes.c_char_p,ctypes.c_void_p];rsvg.rsvg_handle_new_from_file.restype=ctypes.c_void_p
   rsvg.rsvg_handle_render_cairo.argtypes=[ctypes.c_void_p,ctypes.c_void_p];rsvg.rsvg_handle_render_cairo.restype=ctypes.c_int
   gobject.g_object_unref.argtypes=[ctypes.c_void_p]
   w=int(float(root.attrib['width'].removesuffix('px')));h=int(float(root.attrib['height'].removesuffix('px')))
   surface=cairo.cairo_image_surface_create(0,w*2,h*2);context=cairo.cairo_create(surface);cairo.cairo_set_source_rgb(context,1,1,1);cairo.cairo_paint(context);cairo.cairo_scale(context,2,2)
   handle=rsvg.rsvg_handle_new_from_file(str(raw).encode(),None);assert handle
   assert rsvg.rsvg_handle_render_cairo(handle,context)
   assert cairo.cairo_surface_write_to_png(surface,str(dst).encode())==0
   gobject.g_object_unref(handle);cairo.cairo_destroy(context);cairo.cairo_surface_destroy(surface)
   method='Installed librsvg/cairo static SVG fallback at 2x dimensions on white; no scripts/external resources; foreignObject text separately extracted and read because fallback labels can truncate'

  else:
   im=Image.open(raw).convert('RGBA');white=Image.new('RGBA',im.size,'white');white.alpha_composite(im);white.convert('RGB').save(dst);method='Pillow alpha-composite onto white at unchanged original pixel dimensions'
  records.append({'number':f['number'],'index':i,'path':str(dst.relative_to(ROOT)),'source_path':str(raw.relative_to(ROOT)),'method':method})
for group in [list(range(1,6)),list(range(6,11)),list(range(11,15)),list(range(15,21)),list(range(24,29)),list(range(29,35)),list(range(35,41))]:
 images=[]
 for r in records:
  if r['number'] not in group:continue
  im=Image.open(ROOT/r['path']);im.thumbnail((1200,1600));images.append((r,im))
 canvas=Image.new('RGB',(1220,sum(im.height+42 for r,im in images)+20),'white');d=ImageDraw.Draw(canvas);y=10
 for r,im in images:d.text((10,y),f'Figure {r["number"]}, asset {r["index"]}',fill='black');y+=30;canvas.paste(im,(10,y));y+=im.height+12
 canvas.save(base/'renders'/f'sheet-{group[0]:02d}-{group[-1]:02d}.png')
(base/'metadata/render-inventory.json').write_text(json.dumps(records,indent=2)+'\n')
print('Rendered',len(records),'figure assets and 7 contact sheets')
