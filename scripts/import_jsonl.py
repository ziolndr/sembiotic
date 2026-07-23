#!/usr/bin/env python3
"""Normalize arbitrary JSON/JSONL/CSV records into the ARBITER Biology corpus schema."""
from __future__ import annotations
import argparse,csv,hashlib,json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('input');ap.add_argument('--output',required=True);ap.add_argument('--source',default='Private imported dataset')
    ap.add_argument('--domain',default='unified');ap.add_argument('--title-field',default='title');ap.add_argument('--text-field',default='text');ap.add_argument('--category-field',default='category')
    a=ap.parse_args();src=Path(a.input);out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    if src.suffix.lower()=='.csv':
        with src.open(newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    elif src.suffix.lower()=='.json':
        data=json.loads(src.read_text(encoding='utf-8'));rows=data if isinstance(data,list) else data.get('rows') or data.get('objects') or [data]
    else:
        for line in src.read_text(encoding='utf-8').splitlines():
            if line.strip():rows.append(json.loads(line))
    n=0
    with out.open('w',encoding='utf-8') as f:
        for r in rows:
            title=str(r.get(a.title_field) or r.get('name') or r.get('id') or '').strip();text=str(r.get(a.text_field) or r.get('description') or title).strip()
            if not title or not text:continue
            rid=str(r.get('id') or 'import:'+hashlib.sha1((title+'\n'+text).encode()).hexdigest()[:18]);category=str(r.get(a.category_field) or 'Imported Biological Object')
            obj={'id':rid,'code':str(r.get('code') or rid[-10:]).upper(),'title':title,'name':title,'text':text,'object_type':category,'category':category,
                 'domain':str(r.get('domain') or a.domain),'mode':str(r.get('mode') or r.get('domain') or a.domain),'source':str(r.get('source') or a.source),
                 'source_url':str(r.get('source_url') or ''),'tenant':str(r.get('tenant') or 'private'),'tags':r.get('tags') or [],'metadata':r}
            f.write(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n');n+=1
    print(f'IMPORTED {n:,} objects -> {out}')
if __name__=='__main__':main()
