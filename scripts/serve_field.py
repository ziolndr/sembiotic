#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, mimetypes, os, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import numpy as np
from embed_client import embed_texts

class Field:
    def __init__(self,field_dir:Path,embed_url:str):
        self.field_dir=field_dir;self.embed_url=embed_url;self.lock=threading.RLock();self.loaded_mtime=0;self.reload()
    def reload(self):
        with self.lock:
            mp=self.field_dir/'manifest.json';vp=self.field_dir/'vectors.npy';op=self.field_dir/'objects.jsonl'
            if not(mp.exists() and vp.exists() and op.exists()):
                self.manifest={'status':'missing','count':0,'dimension':72,'domains':{},'categories':{},'sources':{}}
                self.vectors=None;self.objects=[];self.loaded_mtime=0;return
            self.manifest=json.loads(mp.read_text());self.vectors=np.load(vp,mmap_mode='r')
            self.objects=[json.loads(x) for x in op.read_text(encoding='utf-8').splitlines() if x.strip()]
            if len(self.objects)!=self.vectors.shape[0]:raise RuntimeError('metadata/vector count mismatch')
            self.loaded_mtime=mp.stat().st_mtime_ns
    def maybe_reload(self):
        mp=self.field_dir/'manifest.json'
        if mp.exists() and mp.stat().st_mtime_ns!=self.loaded_mtime:self.reload()
    def search(self,query:str,limit:int=24,mode:str|None=None,categories=None,sources=None):
        self.maybe_reload()
        if self.vectors is None:raise RuntimeError('field not built')
        t0=time.perf_counter();q=np.asarray(embed_texts(self.embed_url,[query],180)[0],dtype=np.float32)
        q/=max(float(np.linalg.norm(q)),1e-12)
        with self.lock:
            mask=None
            if mode and mode!='unified':mask=np.fromiter((str(o.get('domain'))==mode for o in self.objects),dtype=bool,count=len(self.objects))
            if categories:
                s=set(categories);m=np.fromiter((str(o.get('category')) in s for o in self.objects),dtype=bool,count=len(self.objects));mask=m if mask is None else mask&m
            if sources:
                s=set(sources);m=np.fromiter((str(o.get('source')) in s for o in self.objects),dtype=bool,count=len(self.objects));mask=m if mask is None else mask&m
            if mask is None:
                idx=np.arange(len(self.objects),dtype=np.int64);scores=np.asarray(self.vectors@q)
            else:
                idx=np.flatnonzero(mask);scores=np.asarray(self.vectors[idx]@q)
            if not len(idx):return {'results':[],'latency_ms':round((time.perf_counter()-t0)*1000),'scanned':0,'count':len(self.objects)}
            k=min(max(1,limit),len(idx));sel=np.argpartition(scores,-k)[-k:];sel=sel[np.argsort(scores[sel])[::-1]]
            rows=[]
            for pos in sel:
                obj=dict(self.objects[int(idx[pos])]);obj['score']=float(scores[pos]);rows.append(obj)
        return {'results':rows,'latency_ms':round((time.perf_counter()-t0)*1000),'scanned':int(len(idx)),'count':len(self.objects),'dimension':int(self.manifest.get('dimension',72)),'field_version':self.manifest.get('version'),'source':'LOCAL 72D FIELD'}

class App(BaseHTTPRequestHandler):
    server_version='ARBITERBiologyField/1.0'
    def log_message(self,fmt,*args):print(time.strftime('%H:%M:%S'),fmt%args)
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin','*');self.send_header('Access-Control-Allow-Headers','Content-Type');self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS')
    def json(self,status,obj):
        data=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self._cors();self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_OPTIONS(self):self.send_response(204);self._cors();self.end_headers()
    def do_GET(self):
        path=urlparse(self.path).path
        if path in ('/field/v1/manifest','/manifest'):
            self.server.field.maybe_reload();return self.json(200,self.server.field.manifest)
        if path in ('/field/v1/health','/health'):
            f=self.server.field;return self.json(200,{'ok':f.vectors is not None,'count':len(f.objects),'embed_url':f.embed_url})
        if path=='/field/v1/reload':
            try:self.server.field.reload();return self.json(200,self.server.field.manifest)
            except Exception as exc:return self.json(500,{'error':str(exc)})
        if path=='/':path='/index.html'
        target=(self.server.public_dir/path.lstrip('/')).resolve()
        if self.server.public_dir.resolve() not in target.parents and target!=self.server.public_dir.resolve():return self.json(403,{'error':'forbidden'})
        if not target.exists() or not target.is_file():return self.json(404,{'error':'not found'})
        data=target.read_bytes();self.send_response(200);self._cors();self.send_header('Content-Type',mimetypes.guess_type(str(target))[0] or 'application/octet-stream');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in ('/field/v1/search','/search'):return self.json(404,{'error':'not found'})
        try:
            n=int(self.headers.get('Content-Length','0'));body=json.loads(self.rfile.read(n) or b'{}');query=str(body.get('query') or '').strip()
            if not query:return self.json(400,{'error':'query required'})
            out=self.server.field.search(query,limit=min(100,int(body.get('limit',24))),mode=body.get('mode'),categories=body.get('categories'),sources=body.get('sources'))
            return self.json(200,out)
        except Exception as exc:return self.json(500,{'error':str(exc)})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=int(os.environ.get('ARBITER_BIOLOGY_PORT','8799')))
    ap.add_argument('--field',default='field');ap.add_argument('--public',default='public');ap.add_argument('--embed-url',default=os.environ.get('ARBITER_EMBED_URL','http://127.0.0.1:8000/v1/embed'))
    a=ap.parse_args();server=ThreadingHTTPServer((a.host,a.port),App);server.field=Field(Path(a.field),a.embed_url);server.public_dir=Path(a.public)
    print(f'ARBITER BIOLOGY FIELD · http://{a.host}:{a.port} · {len(server.field.objects):,} objects · embed {a.embed_url}')
    server.serve_forever()
if __name__=='__main__':main()
