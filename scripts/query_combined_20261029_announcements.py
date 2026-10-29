"""Bounded exact-code original filings; an empty query is not risk clearance."""
from concurrent.futures import ThreadPoolExecutor
from collect_combined_20261029 import get,stamp,ROOT
import json
NAMES={'600118':'中国卫星','300900':'广联航空','002149':'西部材料','600643':'爱建集团','002275':'桂林三金','603382':'海阳科技','603279':'景津装备','600501':'航天晨光','600728':'佳都科技','002943':'宇晶股份','603131':'上海沪工','002708':'光洋股份','001219':'青岛食品','000678':'襄阳轴承','605179':'一鸣食品','603699':'纽威股份','603926':'铁流股份','000554':'泰山石油','603703':'盛洋科技','002172':'澳洋健康','001379':'腾达科技','600576':'祥源文旅'}
def query(item):
 c,n=item;q={'pageNum':1,'pageSize':50,'column':'sse' if c.startswith('6') else 'szse','tabName':'fulltext','stock':'','searchkey':n,'seDate':'2026-10-01~2026-10-30','isHLtitle':'true'}
 r=get('https://www.cninfo.com.cn/new/hisAnnouncement/query',q,post=True);r['query']=q;r['code']=c;r['exact_code_rows']=[a for a in (r.get('payload',{}).get('announcements') or []) if a.get('secCode')==c];return c,r
with ThreadPoolExecutor(max_workers=3) as p:rows=dict(p.map(query,NAMES.items()))
(ROOT/'tmp/combined-20261029-announcements.json').write_text(json.dumps({'retrieved_at':stamp(),'items':rows},ensure_ascii=False,indent=2))
print(json.dumps({c:{'ok':r['ok'],'has_more':r.get('payload',{}).get('hasMore'),'rows':[(a['announcementTitle'],a['adjunctUrl']) for a in r['exact_code_rows'][:8]]} for c,r in rows.items()},ensure_ascii=False))
