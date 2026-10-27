"""Archive bounded official queries with exact-code checks, not filing clearance."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from collect_combined_20261027 import get, stamp, ROOT
NAMES={'600826':'兰生股份','000888':'峨眉山','600626':'申达股份','002823':'凯中精密','002187':'广百股份','300961':'深水海纳','301083':'百胜智能','600838':'上海九百','000678':'襄阳轴承','603028':'赛福天','603528':'多伦科技','002724':'海洋王','002535':'林州重机','000559':'万向钱潮','001219':'青岛食品','002991':'甘源食品','603007':'顺景科技','001318':'阳光乳业','002820':'桂发祥','600785':'新华百货','601086':'国芳集团','002249':'大洋电机'}
def one(item):
    c,n=item
    q={'pageNum':1,'pageSize':50,'column':'sse' if c.startswith('6') else 'szse','tabName':'fulltext','stock':'','searchkey':n,'seDate':'2026-10-01~2026-10-28','isHLtitle':'true'}
    r=get('https://www.cninfo.com.cn/new/hisAnnouncement/query',q,post=True)
    p=r.get('payload') or {}
    r['query']=q;r['code']=c;r['exact_code_rows']=[a for a in (p.get('announcements') or []) if a.get('secCode')==c]
    return c,r
with ThreadPoolExecutor(max_workers=4) as ex:out=dict(ex.map(one,NAMES.items()))
(ROOT/'tmp/combined-20261027-announcements.json').write_text(json.dumps({'retrieved_at':stamp(),'items':out},ensure_ascii=False,indent=2))
for c,r in out.items():
    print(c,NAMES[c],r['ok'],'hasMore',(r.get('payload') or {}).get('hasMore'),[(x['announcementTitle'],x['adjunctUrl']) for x in r['exact_code_rows']],flush=True)
