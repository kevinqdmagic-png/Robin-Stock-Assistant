"""Retrieve original filings with hashes and actual availability evidence."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from datetime import datetime,timezone
import json,hashlib,re
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
def stamp():return datetime.now(timezone.utc).isoformat()
q=json.loads((ROOT/'tmp/combined-20261029-announcements.json').read_text())['items']
selected={}
for c,r in q.items():
 for a in r['exact_code_rows']:
  title=re.sub('<[^>]+>','',a['announcementTitle'])
  if '报告' in title and ('三季度' in title or '第三季度' in title) and not any(x in title for x in ['提示','经营','说明会']):selected[c+'-q3']=(title,'https://static.cninfo.com.cn/'+a['adjunctUrl']);break
for c,terms in {'002275':['利润分配','资产减值'],'603279':['利润分配'],'001219':['风险提示'],'002943':['补充质押'],'600576':['立案'],'002708':['异常波动'],'605179':['权益分派']}.items():
 for term in terms:
  a=next((a for a in q[c]['exact_code_rows'] if term in a['announcementTitle']),None)
  if a:selected[c+'-'+term]=(re.sub('<[^>]+>','',a['announcementTitle']),'https://static.cninfo.com.cn/'+a['adjunctUrl'])
p=ROOT/'tmp/pdfs/combined-20261029';p.mkdir(parents=True,exist_ok=True)
def one(item):
 key,(title,url)=item;r={'source':url,'title':title,'retrieval_started_at':stamp()}
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20) as f:b=f.read()
  r.update(ok=True,retrieved_at=stamp(),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b));path=p/(key+'.pdf');path.write_bytes(b);reader=PdfReader(path);text='\n'.join(page.extract_text() or '' for page in reader.pages);(p/(key+'.txt')).write_text(text);r.update(page_count=len(reader.pages),text=text)
 except Exception as e:r.update(ok=False,retrieved_at=stamp(),error=repr(e))
 return key,r
with ThreadPoolExecutor(max_workers=3) as pool:out=dict(pool.map(one,selected.items()))
(ROOT/'tmp/combined-20261029-official-files.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({k:{a:v for a,v in r.items() if a!='text'} for k,r in out.items()},ensure_ascii=False))
