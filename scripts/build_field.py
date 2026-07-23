#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
from collections import Counter
from pathlib import Path
import numpy as np
from embed_client import embed_texts

def iter_jsonl(paths):
    for path in paths:
        with path.open(encoding='utf-8') as f:
            for lineno,line in enumerate(f,1):
                line=line.strip()
                if not line:continue
                try: obj=json.loads(line)
                except Exception as exc: raise RuntimeError(f'{path}:{lineno}: {exc}')
                if not isinstance(obj,dict):continue
                title=str(obj.get('title') or obj.get('name') or obj.get('code') or '').strip()
                text=str(obj.get('text') or obj.get('description') or '').strip()
                if not text:text=title
                if not title or not text:continue
                obj['title']=title;obj['name']=str(obj.get('name') or title);obj['text']=text
                obj.setdefault('id',hashlib.sha1((title+'\n'+text).encode()).hexdigest())
                obj.setdefault('code',str(obj['id'])[-10:].upper())
                obj.setdefault('category',str(obj.get('object_type') or 'Biological Object'))
                obj.setdefault('object_type',obj['category'])
                obj.setdefault('domain',str(obj.get('mode') or 'unified'))
                obj.setdefault('mode',obj['domain'])
                obj.setdefault('source','Imported corpus')
                obj.setdefault('source_url','')
                obj.setdefault('tenant','public')
                obj.setdefault('tags',[])
                obj.setdefault('metadata',{})
                yield obj

def fingerprint(paths):
    h=hashlib.sha256()
    for p in paths:
        h.update(str(p.name).encode());h.update(str(p.stat().st_size).encode());h.update(str(p.stat().st_mtime_ns).encode())
    return h.hexdigest()

def write_json(path,obj):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False));tmp.replace(path)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--corpus',default='corpus')
    ap.add_argument('--field',default='field')
    ap.add_argument('--embed-url',default=os.environ.get('ARBITER_EMBED_URL','http://127.0.0.1:8000/v1/embed'))
    ap.add_argument('--batch-size',type=int,default=int(os.environ.get('ARBITER_EMBED_BATCH','64')))
    ap.add_argument('--timeout',type=float,default=180)
    ap.add_argument('--fresh',action='store_true')
    args=ap.parse_args()
    corpus=Path(args.corpus);field=Path(args.field);field.mkdir(parents=True,exist_ok=True)
    paths=sorted(p for p in corpus.glob('*.jsonl') if p.is_file())
    if not paths:raise SystemExit(f'no JSONL corpus files in {corpus}')
    fp=fingerprint(paths)
    seen_ids=set();seen_text=set();records=[]
    for obj in iter_jsonl(paths):
        rid=str(obj['id']);tkey=' '.join(obj['text'].lower().split())
        if rid in seen_ids or tkey in seen_text:continue
        seen_ids.add(rid);seen_text.add(tkey);records.append(obj)
    if not records:raise SystemExit('corpus contains no usable objects')
    metadata_path=field/'objects.jsonl';vectors_path=field/'vectors.npy';progress_path=field/'build-progress.json';manifest_path=field/'manifest.json'
    start=0;arr=None;dim=None
    if not args.fresh and progress_path.exists() and vectors_path.exists():
        try:
            state=json.loads(progress_path.read_text())
            if state.get('fingerprint')==fp and state.get('count')==len(records):
                arr=np.load(vectors_path,mmap_mode='r+');dim=int(arr.shape[1]);start=int(state.get('next_index',0))
                print(f'resuming at {start:,}/{len(records):,} · {dim}D')
        except Exception as exc: print(f'ignoring invalid checkpoint: {exc}',file=sys.stderr)
    if start==0:
        for p in (vectors_path,progress_path,manifest_path):
            if p.exists():p.unlink()
        with metadata_path.open('w',encoding='utf-8') as f:
            for obj in records:f.write(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n')
        first=records[:min(args.batch_size,len(records))]
        print(f'probing {args.embed_url} with {len(first)} object(s)...')
        rows=embed_texts(args.embed_url,[x['text'] for x in first],args.timeout)
        dim=len(rows[0])
        arr=np.lib.format.open_memmap(vectors_path,mode='w+',dtype='float32',shape=(len(records),dim))
        block=np.asarray(rows,dtype=np.float32);norm=np.linalg.norm(block,axis=1,keepdims=True);block/=np.maximum(norm,1e-12);arr[:len(first)]=block;arr.flush()
        start=len(first)
        write_json(progress_path,{'fingerprint':fp,'count':len(records),'dimension':dim,'next_index':start,'embed_url':args.embed_url})
    t0=time.time()
    for i in range(start,len(records),args.batch_size):
        batch=records[i:i+args.batch_size]
        rows=embed_texts(args.embed_url,[x['text'] for x in batch],args.timeout)
        block=np.asarray(rows,dtype=np.float32)
        if block.ndim!=2 or block.shape[1]!=dim:raise RuntimeError(f'dimension changed at {i}: {block.shape}')
        norm=np.linalg.norm(block,axis=1,keepdims=True);block/=np.maximum(norm,1e-12)
        arr[i:i+len(batch)]=block;arr.flush()
        nxt=i+len(batch);write_json(progress_path,{'fingerprint':fp,'count':len(records),'dimension':dim,'next_index':nxt,'embed_url':args.embed_url})
        elapsed=max(.001,time.time()-t0);rate=max(1,(nxt-start)/elapsed);remain=(len(records)-nxt)/rate
        print(f'embedded {nxt:,}/{len(records):,} · {rate:,.1f}/s · ETA {remain/60:.1f}m',flush=True)
    domains=Counter(str(x.get('domain') or 'unified') for x in records);cats=Counter(str(x.get('category') or 'Biological Object') for x in records);sources=Counter(str(x.get('source') or 'Imported corpus') for x in records)
    manifest={
        'status':'ready','name':'ARBITER Biology Field','version':time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()),'count':len(records),'dimension':dim,
        'embedding_url':args.embed_url,'corpus_fingerprint':fp,'built_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'domains':dict(domains),'categories':dict(cats.most_common()),'sources':dict(sources.most_common()),
        'vector_bytes':int(vectors_path.stat().st_size),'metadata_bytes':int(metadata_path.stat().st_size),
        'score_mode':'normalized dot product','raw_assets_retained':True
    }
    write_json(manifest_path,manifest)
    if progress_path.exists():progress_path.unlink()
    print(f'FIELD READY · {len(records):,} objects · {dim}D · {vectors_path.stat().st_size/1024/1024:.1f} MB')
if __name__=='__main__':main()
