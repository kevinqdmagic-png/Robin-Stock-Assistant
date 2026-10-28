"""Bounded exact-code original filings; an empty query is not risk clearance."""
from concurrent.futures import ThreadPoolExecutor
from collect_combined_20261028 import get,stamp,ROOT
import json
NAMES={'603699':'纽威股份','000554':'泰山石油','603633':'徕木股份','603109':'神驰机电','600078':'澄星股份','300549':'优德精密','300539':'横河精密','300980':'祥源新材','001296':'长江材料','603926':'铁流股份','605488':'福莱新材','603337':'杰克科技','000678':'襄阳轴承','001219':'青岛食品','002708':'光洋股份','600838':'上海九百','603028':'赛福天','603528':'多伦科技','002823':'凯中精密','000888':'峨眉山A'}
def query(item):
 c,n=item;q={'pageNum':1,'pageSize':50,'column':'sse' if c.startswith('6') else 'szse','tabName':'fulltext','stock':'','searchkey':n,'seDate':'2026-10-01~2026-10-29','isHLtitle':'true'}
 r=get('https://www.cninfo.com.cn/new/hisAnnouncement/query',q,post=True);r['query']=q;r['code']=c;r['exact_code_rows']=[a for a in (r.get('payload',{}).get('announcements') or []) if a.get('secCode')==c];return c,r
with ThreadPoolExecutor(max_workers=3) as p:rows=dict(p.map(query,NAMES.items()))
(ROOT/'tmp/combined-20261028-announcements.json').write_text(json.dumps({'retrieved_at':stamp(),'items':rows},ensure_ascii=False,indent=2))
print(json.dumps({c:{'ok':r['ok'],'has_more':r.get('payload',{}).get('hasMore'),'rows':[(a['announcementTitle'],a['adjunctUrl']) for a in r['exact_code_rows'][:8]]} for c,r in rows.items()},ensure_ascii=False))
