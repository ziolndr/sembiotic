#!/usr/bin/env python3
from __future__ import annotations
import json, urllib.request, urllib.error
from typing import Iterable

class EmbedError(RuntimeError): pass

def _parse_vectors(payload, expected:int):
    obj=payload
    if isinstance(obj, dict):
        for key in ('embeddings','vectors','data','results','output'):
            if key in obj:
                obj=obj[key]; break
        else:
            if 'embedding' in obj: obj=[obj['embedding']]
            elif 'vector' in obj: obj=[obj['vector']]
    if isinstance(obj, dict):
        obj=[obj]
    if not isinstance(obj, list):
        raise EmbedError(f'unrecognized embedding response type: {type(obj).__name__}')
    if obj and isinstance(obj[0], dict):
        out=[]
        for item in obj:
            if 'embedding' in item: out.append(item['embedding'])
            elif 'vector' in item: out.append(item['vector'])
            elif 'values' in item: out.append(item['values'])
            else: raise EmbedError('embedding item missing embedding/vector/values')
        obj=out
    if expected==1 and obj and isinstance(obj[0], (int,float)):
        obj=[obj]
    if len(obj)!=expected:
        raise EmbedError(f'expected {expected} embeddings, received {len(obj)}')
    clean=[]
    dim=None
    for vec in obj:
        if not isinstance(vec,list) or not vec:
            raise EmbedError('embedding vector is empty or invalid')
        row=[float(x) for x in vec]
        dim=dim or len(row)
        if len(row)!=dim: raise EmbedError('inconsistent embedding dimensions')
        clean.append(row)
    return clean

def _post(url:str,payload:dict,timeout:float):
    req=urllib.request.Request(url,data=json.dumps(payload).encode('utf-8'),headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=timeout) as res:
        return json.loads(res.read().decode('utf-8'))

def embed_texts(url:str,texts:Iterable[str],timeout:float=120.0):
    texts=[str(x) for x in texts]
    if not texts:return []
    attempts=[
        {'input':texts},
        {'texts':texts},
        {'sentences':texts},
        {'inputs':texts},
    ]
    errors=[]
    for payload in attempts:
        try:return _parse_vectors(_post(url,payload,timeout),len(texts))
        except Exception as exc: errors.append(f'{next(iter(payload))}: {exc}')
    if len(texts)>1:
        rows=[]
        for text in texts:
            single_errors=[]
            for payload in ({'input':text},{'text':text},{'sentence':text},{'inputs':[text]},{'texts':[text]}):
                try:
                    rows.extend(_parse_vectors(_post(url,payload,timeout),1));break
                except Exception as exc: single_errors.append(f'{next(iter(payload))}: {exc}')
            else: raise EmbedError('single-item embedding failed: '+' | '.join(single_errors[-3:]))
        return rows
    raise EmbedError('embedding failed: '+' | '.join(errors[-4:]))
