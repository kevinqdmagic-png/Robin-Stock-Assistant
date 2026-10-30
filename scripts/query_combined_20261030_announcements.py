"""Original filings for actual comparison candidates; empty is not clearance."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from collect_combined_20261030 import ROOT,CACHE,get,stamp,save
NAMES={'000568':'泸州老窖','000596':'古井贡酒','002432':'九安医疗','000716':'黑芝麻','002365':'永安药业','600285':'羚锐制药','605338':'巴比食品','603233':'大参林','600258':'首旅酒店','603703':'盛洋科技','600261':'阳光照明','003032':'传智教育','002275':'桂林三金','001219':'青岛食品','603278':'大业股份','002086':'东方海洋','002172':'澳洋健康','000995':'皇台酒业','603198':'迎驾贡酒','603369':'今世缘','600118':'中国卫星','603279':'景津装备','603382':'海阳科技','002724':'海洋王'}
def one(item):
 c,n=item;q={'pageNum':1,'pageSize':50,'column':'sse' if c.startswith('6') else 'szse','tabName':'fulltext','stock':'','searchkey':n,'seDate':'2026-10-01~2026-10-31','isHLtitle':'true'}
 r=get('https://www.cninfo.com.cn/new/hisAnnouncement/query',q,post=True);r['query']=q;r['code']=c
 r['exact_code_rows']=[a for a in (r.get('payload',{}).get('announcements') or []) if a.get('secCode')==c]
 save(CACHE/'announcements'/(c+'.json'),r)
 return c,r
if __name__=='__main__':
 import json
 with ThreadPoolExecutor(max_workers=3) as p:rows=dict(p.map(one,NAMES.items()))
 save(ROOT/'tmp/combined-20261030-announcements.json',{'retrieved_at':stamp(),'items':rows})
 print(json.dumps({c:{'ok':r['ok'],'has_more':r.get('payload',{}).get('hasMore'),'rows':[(a['announcementTitle'],a['adjunctUrl']) for a in r['exact_code_rows'][:6]]} for c,r in rows.items()},ensure_ascii=False),flush=True)
