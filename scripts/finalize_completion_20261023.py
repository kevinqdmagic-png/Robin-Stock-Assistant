"""Finalize the supplemental Beijing quote check before initial publication."""
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo
import gzip,json,re

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT.parent/'task_audit_20261023'
def load(p):return json.loads((ROOT/p).read_text())
def save(p,v):(ROOT/p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def pct(a,b):return round((a/b-1)*100,3)

def main():
    ep=ROOT/'docs/research/completion-20261023-evidence.json.gz'
    e=json.loads(gzip.decompress(ep.read_bytes()))
    if e.get('beijing_quote_validation'):raise RuntimeError('Already finalized; preserve frozen publication')
    text=(AUDIT/'beijing_previous_quotes.txt').read_text()
    quotes={}
    for code,body in re.findall(r'v_bj(\d+)="([^"]+)"',text):
        x=body.split('~');assert x[30].startswith('20261023')
        quotes[code]={'code':code,'name':x[1],'close':float(x[3]),'previous_close':float(x[4]),
                      'open':float(x[5]),'high':float(x[33]),'low':float(x[34]),'quote_time':x[30]}
    assert len(quotes)==5
    source='https://qt.gtimg.cn/q=bj920096,bj920157,bj920196,bj920229,bj920296'
    stamp=datetime.now(timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    for r in e['dragon_previous_validations']:
        if r['status']!='missing_daily':continue
        q=quotes[r['code']];cur=e['daily_histories'][r['code']]['bars'][-1]
        assert all(abs(q[k]-cur[k])<0.011 for k in ('open','high','low','close'))
        r.update(status='price_observed_using_dated_previous_close_quote',base_date='2026-10-22',base_close=q['previous_close'],
                 open_pct=pct(q['open'],q['previous_close']),close_pct=pct(q['close'],q['previous_close']),
                 mfe_pct=pct(q['high'],q['previous_close']),mae_pct=pct(q['low'],q['previous_close']),
                 daily=cur,source=source,quote_time=q['quote_time'],executed_trade=False,executable_net_return_pct=None,
                 scope='Beijing30pct_separate_group',limitation='Only dated previous close and T candle, not full historical daily path')
    assert len(e['dragon_previous_validations'])==38 and all('close_pct' in x for x in e['dragon_previous_validations'])
    groups={}
    for r in e['dragon_previous_validations']:
        c=r['code'];g='北交所30%' if c.startswith(('4','8','9')) else '创业科创20%' if c.startswith(('30','68')) else '普通主板10%'
        groups.setdefault(g,[]).append(r['close_pct'])
    e['dragon_previous_by_board']={k:{'count':len(v),'mean_close_pct':round(mean(v),3),'median_close_pct':round(median(v),3),'positive_n':sum(x>0 for x in v)} for k,v in groups.items()}
    e['beijing_quote_validation']={'source':source,'retrieved_at':stamp,'raw_response':text,'parsed':quotes,'full_historical_daily_available':False}
    e['volume_method_audit']={'prior_window':'T-excluded available qfq bars; N may exceed available history',
       'new_window':'unadjusted MA/range including T; requires N complete bars',
       'short_history_codes':[x['code'] for x in e['recomputed_broad_pool'] if x['range_position_pct']['120'] is None],
       'frozen_original_records_changed':False}
    e['actual_completed_at']=stamp
    ep.write_bytes(gzip.compress(json.dumps(e,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0))
    research=load('backend/data/research.json');runs=load('backend/data/task_runs.json')
    grouptext='\n\n补充：上述上一名单并集实际38只，其中沪深33只已有完整日线，北交所5只接口只有T一根K线。现已另取带20261023时间的报价前收与T日OHLC逐项核对，补齐5只的一日价格观察；不称其历史K线已完整。所有38只均留档，分制度统计如下：\n\n|组别|样本数|收盘观察均值%|中位数%|收红数|\n|---|---|---|---|---|\n'
    for k,v in e['dragon_previous_by_board'].items():grouptext+=f"|{k}|{v['count']}|{v['mean_close_pct']}|{v['median_close_pct']}|{v['positive_n']}|\n"
    grouptext+='\n北交所补充逐股：\n\n|代码/名称|22日前收|23日开盘%|收盘%|最高/最低观察%|\n|---|---|---|---|---|\n'
    for r in e['dragon_previous_validations']:
        if r['code'] in quotes:grouptext+=f"|{r['code']} {r['name']}|{r['base_close']}|{r['open_pct']}|{r['close_pct']}|{r['mfe_pct']}/{r['mae_pct']}|\n"
    for r in research['items']:
        if not r.get('run_id','').endswith('20261023-manual-completion-v1'):continue
        r.update(published_at=stamp,recorded_at=stamp)
        r['body']=re.sub(r'实际补做完成时间[^。]+', '实际补做完成时间'+stamp, r['body'])
        if r['task_id']=='dragon_tiger':
            r['title']='龙虎榜｜8只席位核对，33只沪深及5只北交旧组验证'
            r['summary']='98理由行/78股票；8只买卖席位与同花顺摘要核对；旧组33只沪深日线＋5只北交前收报价验证，分制度统计。'
            r['body']=r['body'].replace('并集33只，全部补齐23日日线','并集38只，其中33只沪深已补齐23日日线')
            r['body']=r['body'].replace('该组包含不同涨跌幅制度，分市场结果见原始逐股证据','这33只包含主板与20%制度，分组结果见补充表和原始逐股证据')
            r['body']+=grouptext;r['sources'].append(source)
        if r['task_id']=='low_dragon':r['body']=r['body'].replace('33只上一观察组验证','33只沪深日线及5只北交前收报价的上一观察组验证')
    for r in runs['items']:
        if r.get('run_id','').endswith('20261023-manual-completion-v1'):
            r.update(recorded_at=stamp,completed_at=stamp)
            if r['task_id']=='dragon_tiger':r['summary']='98理由行/78股票；8只席位核对；旧组38只一日价格验证，沪深与北交分制度保存，候选0。'
    save('backend/data/research.json',research);save('backend/data/task_runs.json',runs)
    new=[r for r in research['items'] if r.get('run_id','').endswith('20261023-manual-completion-v1')]
    doc='# 2026年10月23日五项任务补齐\n\n实际完成：'+stamp+'。只补研究及可核验观察，不回填盘中推荐。\n\n'
    for r in new:doc+='## '+r['title']+'\n\n'+r['body']+'\n\n来源：\n\n'+'\n'.join('- '+str(x) for x in r['sources'])+'\n\n'
    original=next(r for r in research['items'] if r['id']=='volume-price-20261023-close-v1')
    doc+='## 复用的同日量价报告\n\n'+original['body']+'\n\n原报告ID：'+original['id']+'；原文保持不变。\n'
    (ROOT/'docs/research/completion-20261023.md').write_text(doc)
    print(json.dumps({'completed_at':stamp,'previous_38_by_board':e['dragon_previous_by_board']},ensure_ascii=False))

if __name__=='__main__':main()
