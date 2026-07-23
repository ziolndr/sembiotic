#!/usr/bin/env python3
"""Crawl public ScienCell pages into normalized ARBITER field objects.

Only publicly reachable page text is collected. The crawler is intentionally conservative,
rate-limited, resumable by URL, and marks every row with source_url.
"""
from __future__ import annotations
import argparse, hashlib, html, json, re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

UA='ARBITER-Biology-Field/1.0 (+local catalog indexing)'
PRODUCT_HINTS=('product','cell','medium','media','reagent','protein','vector','array','assay','kit','neuron','stem','genequery','qpcr','rna')
SKIP_EXT=('.jpg','.jpeg','.png','.gif','.svg','.webp','.pdf','.zip','.css','.js','.xml')

class TextParser(HTMLParser):
    def __init__(self):super().__init__();self.skip=0;self.parts=[];self.title=[];self.in_title=False
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg'):self.skip+=1
        if tag=='title':self.in_title=True
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg') and self.skip:self.skip-=1
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.skip:return
        t=' '.join(data.split())
        if not t:return
        self.parts.append(t)
        if self.in_title:self.title.append(t)

def fetch(url,timeout=30):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/xml;q=0.9,*/*;q=0.8'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read(),r.headers.get_content_type()

def sitemap_urls(base,max_urls):
    candidates=[]
    try:
        raw,_=fetch(urllib.parse.urljoin(base,'/robots.txt'))
        for line in raw.decode('utf-8','ignore').splitlines():
            if line.lower().startswith('sitemap:'):candidates.append(line.split(':',1)[1].strip())
    except Exception:pass
    candidates += [urllib.parse.urljoin(base,'/sitemap.xml'),urllib.parse.urljoin(base,'/sitemap_index.xml')]
    seen_maps=set();seen_urls=set();queue=list(dict.fromkeys(candidates))
    while queue and len(seen_urls)<max_urls:
        sm=queue.pop(0)
        if sm in seen_maps:continue
        seen_maps.add(sm)
        try:raw,_=fetch(sm);root=ET.fromstring(raw)
        except Exception:continue
        locs=[(x.text or '').strip() for x in root.iter() if x.tag.rsplit('}',1)[-1]=='loc' and x.text]
        if root.tag.rsplit('}',1)[-1]=='sitemapindex':
            queue.extend(x for x in locs if x not in seen_maps)
        else:
            for u in locs:
                if len(seen_urls)>=max_urls:break
                p=urllib.parse.urlparse(u)
                if p.netloc and p.netloc!=urllib.parse.urlparse(base).netloc:continue
                if p.path.lower().endswith(SKIP_EXT):continue
                seen_urls.add(u)
    return list(seen_urls)

def parse_page(url,raw):
    text=raw.decode('utf-8','ignore')
    parser=TextParser();parser.feed(text)
    title=' '.join(parser.title).strip()
    og=re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:title|twitter:title)["\'][^>]+content=["\']([^"\']+)',text,re.I)
    if og:title=html.unescape(og.group(1)).strip()
    desc=''
    for pat in (r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)'):
        m=re.search(pat,text,re.I)
        if m:desc=html.unescape(m.group(1)).strip();break
    body=' '.join(parser.parts)
    body=re.sub(r'\s+',' ',html.unescape(body)).strip()
    if len(body)>6000:body=body[:6000]
    path=urllib.parse.urlparse(url).path.lower()
    category='ScienCell Public Page'
    if any(x in path for x in ('product','catalog')) or any(h in (title+' '+desc).lower() for h in PRODUCT_HINTS):category='ScienCell Catalog Object'
    catno=''
    m=re.search(r'(?:cat(?:alog)?\.?\s*(?:no\.?|number)?|sku)\s*[:#]?\s*([A-Z]{0,4}\d{2,8}[A-Z0-9-]*)',body,re.I)
    if m:catno=m.group(1)
    clean_title=re.sub(r'\s*[|–-]\s*ScienCell.*$','',title,flags=re.I).strip() or urllib.parse.unquote(path.rstrip('/').split('/')[-1]).replace('-',' ').title()
    combined=' '.join(x for x in (clean_title,desc,body) if x)
    if len(combined)<120:return None
    rid='sciencell:'+hashlib.sha1(url.encode()).hexdigest()[:18]
    return {'id':rid,'code':catno or rid.split(':')[1][:10].upper(),'title':clean_title,'name':clean_title,'text':combined,
            'object_type':category,'category':category,'domain':'experiment','mode':'experiment','source':'ScienCell public catalog','source_url':url,
            'tenant':'public','tags':['ScienCell','catalog']+([catno] if catno else []),'metadata':{'catalog_number':catno,'crawled_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',default='https://sciencellonline.com');ap.add_argument('--output',default='corpus/sciencell_public.jsonl')
    ap.add_argument('--max-pages',type=int,default=1200);ap.add_argument('--delay',type=float,default=.12);ap.add_argument('--timeout',type=float,default=30)
    a=ap.parse_args();out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    existing={}
    if out.exists():
        for line in out.read_text(encoding='utf-8').splitlines():
            try:o=json.loads(line);existing[o.get('source_url')]=o
            except Exception:pass
    urls=sitemap_urls(a.base,a.max_pages)
    if not urls:
        urls=[urllib.parse.urljoin(a.base,'/')]
    print(f'discovered {len(urls):,} public URL(s)')
    rows=dict(existing);ok=0;fail=0
    for i,url in enumerate(urls,1):
        if url in rows:continue
        try:
            raw,ctype=fetch(url,a.timeout)
            if 'html' not in ctype:continue
            obj=parse_page(url,raw)
            if obj:rows[url]=obj;ok+=1
        except Exception as exc:
            fail+=1
            if fail<10:print(f'WARN {url}: {exc}')
        if i%25==0:
            with out.open('w',encoding='utf-8') as f:
                for obj in rows.values():f.write(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n')
            print(f'crawled {i:,}/{len(urls):,} · usable {len(rows):,} · failures {fail:,}')
        time.sleep(a.delay)
    with out.open('w',encoding='utf-8') as f:
        for obj in rows.values():f.write(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n')
    print(f'SCIENCELL PUBLIC CORPUS · {len(rows):,} objects -> {out}')
if __name__=='__main__':main()
