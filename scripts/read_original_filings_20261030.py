"""Checkpoint original PDFs and metadata; no PDF full text is published."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from urllib.request import Request,urlopen
import hashlib,json,re,subprocess,sys
from collect_combined_20261030 import ROOT,CACHE,save,stamp
def load(p):return json.loads(p.read_text())
def selected():
 queries={**load(ROOT/'tmp/combined-20261030-announcements.json')['items'],**load(ROOT/'tmp/combined-20261030-extra-announcements.json')['items']}
 codes=['000568','000596','002432','600258','605338','600510','002582','600688','600928','603278','002275','002086','002172','003032','603703','600261','002724','300980','002636']
 files={}
 for c in codes:
  rows=queries[c]['exact_code_rows']
  q3=next((a for a in rows if ('三季度报告' in a['announcementTitle'] or '第三季度报告' in a['announcementTitle']) and '摘要' not in a['announcementTitle']),None)
  if q3:files[c+'-q3']=q3
  risks=[a for a in rows if any(k in a['announcementTitle'] for k in ['严重异常','异常波动','风险提示','减值准备','部分股份质押','利润分配方案'])]
  if c in ['605338','603278','600510','003032','603703','600261','002582']:
   for n,a in enumerate(risks[:2]):files[c+'-risk'+str(n+1)]=a
 # The known high-board/control transaction uncertainty is retained.
 files['001219-risk']=queries['001219']['exact_code_rows'][0]
 return files
def fetch(pair):
 key,a=pair;meta=CACHE/'official-files'/(key+'.json')
 if meta.exists():return key,load(meta)
 folder=ROOT/'tmp/pdfs/combined-20261030';folder.mkdir(parents=True,exist_ok=True)
 url='https://static.cninfo.com.cn/'+a['adjunctUrl']; pdf=folder/(key+'.pdf');text=pdf.with_suffix('.txt')
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20) as f:raw=f.read();status=f.status
  if not raw.startswith(b'%PDF'):raise ValueError('not a PDF response')
  when=stamp();pdf.write_bytes(raw)
  subprocess.run(['pdftotext','-layout',str(pdf),str(text)],check=True,capture_output=True)
  r={'ok':True,'source':url,'title':re.sub('<[^>]*>','',a['announcementTitle']),'announcement_date_metadata':a.get('announcementTime'),
     'retrieved_at':when,'HTTP_status':status,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
     'local_pdf':str(pdf.relative_to(ROOT)),'local_text':str(text.relative_to(ROOT)),
     'availability_note':'Actual HTTP-success time is the verified latest public availability; date in URL is not claimed to be exact first publication time.'}
 except Exception as e:r={'ok':False,'source':url,'retrieved_at':stamp(),'error':repr(e)}
 save(meta,r);return key,r
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=3) as p:rows=dict(p.map(fetch,selected().items()))
 save(ROOT/'tmp/combined-20261030-official-files.json',rows)
 print(json.dumps({'requested':len(rows),'ok':sum(r['ok'] for r in rows.values()),'files':{k:{a:v for a,v in r.items() if a in ['ok','source','error']} for k,r in rows.items()}},ensure_ascii=False),flush=True)
