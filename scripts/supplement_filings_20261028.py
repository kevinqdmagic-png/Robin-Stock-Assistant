"""Fetch original filings for candidate/counterexample checks; preserve availability."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen
from collect_combined_20261028 import ROOT,get,stamp
import hashlib,json,subprocess
folder=ROOT/'tmp/pdfs/combined-20261028';folder.mkdir(parents=True,exist_ok=True)
requests={
 '000554-q3':'finalpage/2026-10-28/1225628047.PDF',
 '000554-dividend':'finalpage/2026-10-13/1225601745.PDF',
 '603699-pledge':'finalpage/2026-10-24/1225618136.PDF',
 '603633-guarantee':'finalpage/2026-10-17/1225607883.PDF',
 '603109-q3':'finalpage/2026-10-29/1225633692.PDF',
 '600078-q3':'finalpage/2026-10-28/1225632289.PDF',
 '600078-impairment':'finalpage/2026-10-28/1225632302.PDF',
 '300549-q3':'finalpage/2026-10-23/1225615170.PDF',
 '300539-q3':'finalpage/2026-10-27/1225625224.PDF',
 '300980-q3':'finalpage/2026-10-27/1225624531.PDF',
 '001296-q3':'finalpage/2026-10-22/1225613941.PDF',
 '603926-q3':'finalpage/2026-10-28/1225627768.PDF',
 '605488-q3':'finalpage/2026-10-29/1225635522.PDF',
 '603337-risk':'finalpage/2026-10-29/1225635883.PDF',
 '000678-q3':'finalpage/2026-10-29/1225632952.PDF',
 '002708-risk':'finalpage/2026-10-28/1225628784.PDF'}
def fetch(item):
 key,path=item;u='https://static.cninfo.com.cn/'+path;p=folder/(key+'.pdf')
 try:
  b=urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=20).read();assert b.startswith(b'%PDF'),b[:25];p.write_bytes(b)
  subprocess.run(['pdftotext','-layout',str(p),str(p.with_suffix('.txt'))],check=True)
  return key,{'ok':True,'source':u,'sha256':hashlib.sha256(b).hexdigest(),'retrieved_at':stamp(),'pdf_path':str(p.relative_to(ROOT)),'text_path':str(p.with_suffix('.txt').relative_to(ROOT))}
 except Exception as e:return key,{'ok':False,'source':u,'error':repr(e),'retrieved_at':stamp()}
with ThreadPoolExecutor(max_workers=3) as p:files=dict(p.map(fetch,requests.items()))
(ROOT/'tmp/combined-20261028-official-files.json').write_text(json.dumps(files,ensure_ascii=False,indent=2))
queries={}
for code,name in [('603699','纽威股份'),('603633','徕木股份'),('000888','峨眉山A')]:
 q={'pageNum':1,'pageSize':50,'column':'sse' if code.startswith('6') else 'szse','tabName':'fulltext','stock':'','searchkey':name,'seDate':'2026-08-01~2026-10-29','isHLtitle':'true'}
 r=get('https://www.cninfo.com.cn/new/hisAnnouncement/query',q,post=True);r['query']=q;r['exact_code_rows']=[a for a in (r.get('payload',{}).get('announcements') or []) if a.get('secCode')==code];queries[code]=r
(ROOT/'tmp/combined-20261028-extra-announcements.json').write_text(json.dumps(queries,ensure_ascii=False,indent=2))
print(json.dumps({'files':{k:r['ok'] for k,r in files.items()},'extended':{c:{'ok':r['ok'],'has_more':r.get('payload',{}).get('hasMore'),'financial':[(a['announcementTitle'],a['adjunctUrl']) for a in r['exact_code_rows'] if '报告' in a['announcementTitle'] or '权益分派' in a['announcementTitle']]} for c,r in queries.items()}},ensure_ascii=False))
