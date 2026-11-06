#!/usr/bin/env python3
"""Append manual T=2026-11-06 research from date-exact public archives.

Never rewrites a freeze, a published report, or an original selection. Publication
and the six full-research gates remain separate. This script makes no network calls.
"""
from collections import Counter, defaultdict
from datetime import datetime, date, timezone
from decimal import Decimal, ROUND_HALF_UP
import gzip
from html import unescape
import importlib.util
import json
from pathlib import Path
import re
import sys
import unicodedata
from statistics import mean, median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from learning_loop import is_session
from strategy_lab import summarize_snapshot

T, D, EXIT = '2026-11-06', '2026-11-09', '2026-11-10'
PREFIX = 'recovery-20261106'
CN = ZoneInfo('Asia/Shanghai')


def read(path):
    return json.loads((ROOT / path).read_text())


def write(path, value):
    (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def table(headers, rows):
    return '\n'.join(['|' + '|'.join(headers) + '|', '|' + '|'.join(['---'] * len(headers)) + '|'] +
                     ['|' + '|'.join(str(v).replace('|', '/').replace('\n', ' ') for v in r) + '|' for r in rows])


def fmt(v, n=3):
    return 'N/A' if v is None else f'{v:.{n}f}'


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def primary_seat_blocks(payload):
    text = '\n'.join(payload['fileContents'])
    assert payload['dateTx'] == T and '2026年11月06日' in text
    pieces = re.split(r'证券代码[:：]\s*(\d{6})\s+证券简称[:：]', text)
    result = defaultdict(list)
    for i in range(1, len(pieces), 2):
        code, chunk = pieces[i], pieces[i + 1]
        sides = chunk.split('买入营业部名称:', 1)[-1].split('卖出营业部名称:', 1)
        if len(sides) != 2:
            continue
        values = []
        for side in sides:
            rows = re.findall(r'^\s*\(\d+\)\s*(.*?)\s+(\d[\d,.]*)\s*$', side, re.M)[:5]
            values.append([(re.sub(r'\s+', '', n), float(v.replace(',', ''))) for n, v in rows])
        result[code].append({'buy': values[0], 'sell': values[1]})
    return result


def main():
    stamp = datetime.now(timezone.utc).astimezone(CN).isoformat(timespec='seconds')
    research = read('backend/data/research.json')
    runs = read('backend/data/task_runs.json')
    assert not any(r['id'] == PREFIX + '-learning_review-v1' for r in research['items'])
    vp = read('docs/research/volume-price-20261106-evidence.json')
    mr = read('docs/research/market-review-20261106-evidence.json')
    minutes = read('docs/research/recovery-20261106-minutes.json')
    raw_lhb = read('docs/research/recovery-20261106-lhb-raw.json')
    exchange = read('docs/research/recovery-20261106-exchange-attempts.json')
    primary = primary_seat_blocks(read('docs/research/recovery-20261106-sse.txt'))
    old = json.loads(gzip.decompress((ROOT / 'docs/research/combined-pair-20261030-evidence.json.gz').read_bytes()))
    nov02 = {r['code']: r for r in read('docs/research/nov02-retrospective-market.json')['rows']}
    snaps = [read(f'backend/data/baostock/2026-11-{d:02d}.json') for d in (3, 4, 5, 6)]
    current = {r['code'].split('.')[-1]: r for r in snaps[-1]['rows']}
    prior = {r['code'].split('.')[-1]: r for r in snaps[-2]['rows']}
    helper = module('scripts/publish_recovery_20261105.py', 'recovery_helper')
    assert len(current) == 5218 and len(vp['broad_pool']) == 120 and len(vp['deep_pool']) == 28
    assert set(minutes['requested']) == {r['code'] for r in vp['deep_pool']}
    assert len(minutes['five_minute']) == 28
    assert all(x['validation']['verified'] for x in minutes['five_minute'].values())
    minute_metrics = {c: helper.minutes_summary(x) for c, x in minutes['five_minute'].items()}
    started = min((minutes['started_at'], raw_lhb['actual_collected_at']), key=datetime.fromisoformat)

    # Full legacy paths are assembled locally; no private list is sent to a vendor.
    ledger = read('backend/data/low_position_samples.json')
    low_paths, path_errors = [], {}
    for sample in ledger['items']:
        code = sample['code']
        hist = old['daily_histories'].get(code, {}).get('bars', [])
        path = {r['date']: {k: r[k] for k in ('open', 'high', 'low', 'close')} for r in hist if r['date'] <= '2026-10-30'}
        if code in nov02:
            r = nov02[code]
            path['2026-11-02'] = {k: r['D_' + k] for k in ('open', 'high', 'low', 'close')}
        for snap in snaps:
            item = next((r for r in snap['rows'] if r['code'].split('.')[-1] == code), None)
            if item:
                path[snap['trade_date']] = {k: item[k] for k in ('open', 'high', 'low', 'close')}
        anchor, cutoff = sample.get('day0_close'), sample.get('invalid_close_below')
        points = sorted((day, r) for day, r in path.items() if sample['date'] < day <= T)
        day0 = date.fromisoformat(sample['date'])
        expected = []
        for ordinal in range(day0.toordinal() + 1, date.fromisoformat(T).toordinal() + 1):
            day = date.fromordinal(ordinal)
            if is_session(day) is True:
                expected.append(day.isoformat())
        missing = sorted(set(expected) - {day for day, _ in points})
        if missing:
            path_errors[sample['id']] = missing
        row = current.get(code)
        if not row or not anchor:
            path_errors[sample['id']] = ['current_bar_or_anchor_missing']
            continue
        closes = [float(anchor)] + [r['close'] for _, r in points]
        peak, dd = closes[0], 0.0
        for value in closes:
            peak = max(peak, value)
            dd = min(dd, (value / peak - 1) * 100)
        obs = {'as_of': T, 'recorded_at': stamp, 'calendar_day': (date.fromisoformat(T) - day0).days,
               'trading_day': len(expected), 'open': row['open'], 'high': row['high'], 'low': row['low'],
               'close': row['close'], 'change_from_day0_pct': (row['close'] / anchor - 1) * 100,
               'maximum_price_excursion_pct': (max([anchor] + [r['high'] for _, r in points]) / anchor - 1) * 100,
               'minimum_price_excursion_pct': (min([anchor] + [r['low'] for _, r in points]) / anchor - 1) * 100,
               'close_path_drawdown_pct': dd,
               'initial_invalidation_triggered': any(r['close'] < cutoff for _, r in points) if cutoff else None,
               'status': 'historical_close_path_observation', 'executed_trade': False,
               'executable_net_return': None, 'day0_comparison_only': True,
               'source': f'backend/data/baostock/{T}.json',
               'path_sources': ['docs/research/combined-pair-20261030-evidence.json.gz',
                                'docs/research/nov02-retrospective-market.json'] +
                               [f'backend/data/baostock/{s["trade_date"]}.json' for s in snaps],
               'path_missing_dates': missing, 'original_snapshot_eligibility_unchanged': True,
               'price_basis': 'unadjusted_daily_prices_not_trade_fills'}
        if not any(x.get('as_of') == T for x in sample.get('observations', [])):
            sample.setdefault('observations', []).append(obs)
        low_paths.append({'id': sample['id'], 'code': code, 'name': sample['name'], 'date': sample['date'],
                          'anchor_close': anchor, 'original_snapshot_verified': sample.get('original_snapshot_verified', False),
                          'original_eligible': sample.get('eligible_for_model_statistics', False), **obs})
    ledger['updated_at'] = stamp
    assert len(low_paths) == 52
    assert not path_errors, path_errors
    write('backend/data/low_position_samples.json', ledger)

    # Retain every disclosure reason, but never add a one-day and three-day board.
    lhb_rows = [r for r in raw_lhb['main_list']['rows'] if r['SECURITY_CODE'].startswith(('0', '3', '6'))]
    assert len(lhb_rows) == 71 and len({r['SECURITY_CODE'] for r in lhb_rows}) == 57
    assert all(r['TRADE_DATE'][:10] == T for r in lhb_rows)
    seat_records = []
    for code in sorted({r['SECURITY_CODE'] for r in lhb_rows}):
        rows = [r for r in lhb_rows if r['SECURITY_CODE'] == code]
        chosen = sorted(rows, key=lambda r: ('连续' in r['EXPLANATION'], -r['BILLBOARD_NET_AMT']))[0]
        record = {'code': code, 'name': chosen['SECURITY_NAME_ABBR'], 'close': chosen['CLOSE_PRICE'],
                  'pct': chosen['CHANGE_RATE'], 'all_reasons': [r['EXPLANATION'] for r in rows],
                  **helper.seat_summary(raw_lhb, chosen)}
        # Reconcile both entire ranked lists to an exact official block where available.
        comparisons = []
        for block in primary.get(code, []):
            checks = []
            for side, field in [('buy', 'BUY'), ('sell', 'SELL')]:
                vendor = sorted(record[side + '_rank_rows'], key=lambda v: -float(v.get(field) or 0))
                official = sorted(block[side], key=lambda v: -v[1])
                normalize = lambda name: unicodedata.normalize('NFKC', re.sub(r'\s+', '', name))
                checks.append(len(vendor) == len(official) and all(
                    normalize(v['OPERATEDEPT_NAME']) == normalize(n) and abs(float(v.get(field) or 0) - value) <= .02
                    for v, (n, value) in zip(vendor, official)))
            comparisons.append(all(checks))
        record['sse_both_ranked_sides_verified'] = any(comparisons)
        record['primary_status'] = 'sse_mainboard_both_sides_exact' if any(comparisons) else 'vendor_copy_only'
        seat_records.append(record)
    exact = [r for r in seat_records if r['sse_both_ranked_sides_verified']]

    # Independent vendor page, kept separate from primary verification.
    html = (ROOT / 'docs/research/recovery-20261106-aijingu.txt').read_text()
    cross_rows = []
    for tr in re.findall(r'<tr\b[^>]*>.*?</tr>', html, re.S):
        cells = [unescape(re.sub('<[^>]+>', ' ', x)).strip() for x in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', tr, re.S)]
        if cells and re.fullmatch(r'\d{6}', cells[0]) and len(cells) >= 11:
            cross_rows.append(cells)
    for record in seat_records:
        matches = [r for r in cross_rows if r[0] == record['code'] and ('连续' in r[10]) == (record['interval'] == 'multi_day')]
        record['aijingu_amount_crosscheck'] = any(
            abs(float(r[6].replace(',', '').replace('+', '')) * 10000 - record['listed_buy_yuan']) <= 105 and
            abs(float(r[7].replace(',', '').replace('+', '')) * 10000 - record['listed_sell_yuan']) <= 105
            for r in matches)

    # Only existing after-close research observations are carried forward. No new
    # original intraday signal, formal recommendation, or simulated fill is created.
    waiting_pair = []
    for old_candidate in vp['after_close_relative_research_pair']:
        code = old_candidate['code']
        waiting_pair.append({'task_id': 'combined_pair', 'code': code,
                             'name': old_candidate['name'], 'reference_price': old_candidate['reference_close'],
                             'reference_as_of': T + 'T15:00:00+08:00', 'actual_frozen_at': old_candidate['freeze_time'],
                             'reviewed_at': stamp, 'planned_observation_date': D,
                             'hypothesis': '原盘后量价观察延续核验；待完整上游后综合评比',
                             'risk': '公告风险与完整板块时点证据未齐；不作最终双标或买入许可',
                             'candidate_status': 'pending_integrated_review_not_final',
                             'formal_buy_signal': False, 'buy_order_allowed': False,
                             'earliest_legal_exit_if_entered': EXIT})
    snapshot = read('backend/data/learning.json')['runs'][-1]
    assert snapshot['date'] == T
    lab = summarize_snapshot(snapshot)
    intraday = {slot: read(f'docs/research/{PREFIX}-{slot}-performance.json') for slot in ('early', 'late')}
    low_candidates = [r for r in vp['broad_pool'] if r.get('position120') is not None and r['position120'] <= .35
                      and r.get('rvol20', 0) >= 1.5 and r['pct'] > 1 and r.get('clv', 0) >= .6]
    low_candidates.sort(key=lambda r: (not r['breakout20'], -r['clv'], r['position120']))
    returns = [r['pctChg'] for r in current.values()]
    evidence = {'trade_date': T, 'planned_observation_date': D, 'started_at': started, 'completed_at': stamp,
                'market_scope': 'Shanghai+Shenzhen; Beijing excluded', 'market_count': len(current),
                'broad_pool_count': 120, 'deep_pool_count': 28, 'verified_minute_count': 28,
                'minute_metrics': minute_metrics, 'old_low_paths': low_paths, 'old_low_missing': path_errors,
                'low_shape_candidates': low_candidates, 'lhb_reason_rows': 71, 'lhb_codes': 57,
                'seat_records': seat_records, 'primary_exact_codes': [r['code'] for r in exact],
                'vendor_amount_crosschecked_codes': sum(r['aijingu_amount_crosscheck'] for r in seat_records),
                'exchange_attempts': exchange, 'learning_snapshot_id': snapshot['id'], 'strategy_lab': lab,
                'intraday_groups': {slot: payload['groups'] for slot, payload in intraday.items()},
                'pending_pair': waiting_pair, 'formal_recommendations_created': 0,
                'original_intraday_records_changed': False, 'actual_trades_verified': 0}
    write('docs/research/recovery-20261106-evidence.json', evidence)

    common = (f'研究交易日T={T}；实际补做完成{stamp}。观察计划D={D}，若D买入最早{EXIT}卖出。'
              '本轮为人工补做，保留所有原报告、原盘中冻结和失败样本，不倒填当时荐股。'
              '日线未复权；RVOL5/10/20分母不含T；五分钟只解释K线之间的顺序，不能证明60秒承接、排队成交或净收益。\n\n')
    min_table = table(['代码', '尾30分钟%', '收盘/VWAP%', '尾30分钟量占比%', '48根及日线核对'], [
        [c, fmt(x['last30_return_pct']), fmt(x['close_vs_vwap_pct']), fmt(x['last30_volume_share'] * 100), '通过']
        for c, x in sorted(minute_metrics.items())])
    shape_table = table(['代码/名称', '收盘', '120日位置%', 'RVOL20', 'CLV', '突破20日高', '反证'], [
        [r['code'] + ' ' + r['name'], fmt(r['close'], 2), fmt(r['position120'] * 100), fmt(r['rvol20']),
         fmt(r['clv']), r['breakout20'], '未收MA60' if r['close'] < r['ma60'] else '行业/公告待核'] for r in low_candidates])
    path_table = table(['旧样本', '原日期/原价', 'T收盘/变化%', '路径高/低%', '收盘最大回撤%', '曾收破原失效', '自然/交易日龄'], [
        [r['code'] + ' ' + r['name'], r['date'] + '/' + fmt(r['anchor_close'], 2),
         fmt(r['close'], 2) + '/' + fmt(r['change_from_day0_pct']),
         fmt(r['maximum_price_excursion_pct']) + '/' + fmt(r['minimum_price_excursion_pct']),
         fmt(r['close_path_drawdown_pct']), r['initial_invalidation_triggered'],
         str(r['calendar_day']) + '/' + str(r['trading_day'])] for r in low_paths])
    seat_table = table(['代码/名称', '披露期', '买/卖/净额(亿元)', '机构披露净额(亿元)', '买一占披露买额%', '两侧官方核对', '独立金额核对'], [
        [r['code'] + ' ' + r['name'], r['interval'],
         '/'.join(fmt(r[k] / 1e8) for k in ('listed_buy_yuan', 'listed_sell_yuan', 'listed_net_yuan')),
         fmt(r['institution_net_yuan'] / 1e8), fmt((r['top_buy_share'] or 0) * 100),
         r['sse_both_ranked_sides_verified'], r['aijingu_amount_crosscheck']] for r in seat_records])
    horizon_table = table(['周期', '证券基准日N', '独立基准日期', '均值%', '中位数%', '正价格比例%', 'MAE<=-5%比例'], [
        ['T+' + h, r['sample_count'], r['unique_anchor_dates'], fmt(r['average_price_change_pct']),
         fmt(r['median_price_change_pct']), fmt(r['positive_pct']), fmt(r['adverse_below_minus_5_pct'])]
        for h, r in lab['horizons'].items()])
    intraday_table = table(['时段', '组别/版本', '周期', 'N/独立日期', '均值%', '正价格比例%'], [
        [slot, r['cohort'] + '/' + r['model_version'], 'T+' + str(r['horizon']),
         str(r['sample_count']) + '/' + str(r['distinct_signal_days']),
         fmt(r['mean_price_change_pct']), fmt(r['positive_price_observation_pct'])]
        for slot, payload in intraday.items() for r in payload['groups']])
    base_sources = ['https://www.baostock.com/',
                    'https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/blob/main/docs/research/recovery-20261106-evidence.json']
    reports = []

    def add(task, title, summary, body, status='partial', full=False, sources=None, **extra):
        rid = PREFIX + '-' + task + '-v1'
        body = common + body
        record = {'id': rid, 'date': T, 'published_at': stamp, 'task_id': task,
                  'track': task if task in ('low_position', 'dragon_tiger', 'volume_price') else 'market_review',
                  'title': title, 'summary': summary, 'body': body, 'sources': sources or base_sources,
                  'status': status, 'analysis_completed': full, 'eligible_for_integrated_research': False,
                  'report_type': 'full_daily_research' if full else 'manual_recovery_research',
                  'provenance': 'manual_delayed_research_not_original_intraday_signal', **extra}
        reports.append(record)
        (ROOT / ('docs/research/' + rid + '.md')).write_text('# ' + title + '\n\n' + body)
        run_id = PREFIX + '-' + task + '-manual-v1'
        runs['items'].append({'id': run_id + '-receipt', 'run_id': run_id, 'task_id': task, 'date': T,
                              'trigger': 'manual', 'started_at': started, 'recorded_at': stamp,
                              'completed_at': stamp, 'status': status, 'summary': summary, 'report_ids': [rid],
                              'analysis_completed': full, 'sources': record['sources']})

    add('volume_price', '11月6日量价补证｜28只五分钟全部校验通过',
        '补齐原深池其余23只历史五分钟；28/28均48根且与独立日线OHLC、量额核对通过，板块时点与成交证据仍缺。',
        '原实质报告volume-price-20261106-partial-v1继续保留；本补充关闭分钟覆盖缺口，不将量价整体改成完整。\n\n' + min_table +
        '\n\n全部28只均保存原始URL、取数时间、响应哈希和逐股日线差异。量与金额相对误差<=1%、OHLC最大差<=0.011元；不是只验证根数。'
        '尾30分钟按(14:30收盘,15:00收盘]，不把14:30那根成交量重复计入尾段。'
        '仍缺逐时全行业成员同步、发行人风险核查和可成交验证，原报告blocked相应项保留。')
    add('low_position', '11月6日低位研究补做｜52条旧样本全路径与新形态对照',
        f'本地归档补齐52条旧样本/51代码截至11月6日全部日线路径；120只广池中保留{len(low_candidates)}只低位量价形态作待核对照。',
        '沪深当日快照5218/5224，原独立广池120只、深池28只。新形态仍是广池内筛选，不称对5218只逐一完成120日历史深查。\n\n' + shape_table +
        '\n\n东方环宇已越20日高且收于MA60之上，较未复MA60的乐山/华银更接近突破结构；但量能骤增也可能是短期交易拥挤。'
        '华银/乐山属于日低修复，不能将低长期位置直接认定吸筹完成。东方电热虽越20日高，较长上影和较低CLV形成反证；'
        '华升封板形态不能倒推可买到。海源复材、中利集团、金螳螂的低位放量下跌作为失败对照，不能只留下上涨者。\n\n' +
        path_table + '\n\n旧52条原始资格均不修改：原未核实快照继续不合格；路径完整不等于原入场可执行。'
        '路径使用已发布10月30日历史、11月2日5094行历史复核及11月3—6日BaoStock；逐一校验交易日集合无缺日。'
        '当日观察逐条追加至low_position_samples.json，不重算旧记录、不消除曾跌破失效事实。'
        '新形态尚缺完整公告/行业同步核验，暂不新增正式30日候选或宣称全市场完整模块。')
    focus = [next(r for r in seat_records if r['code'] == c) for c in ('601595', '300118', '300686', '002696', '000530')]
    focus_text = '\n'.join('- ' + r['code'] + ' ' + r['name'] + '：' + r['interval'] + '披露净额' + fmt(r['listed_net_yuan'] / 1e8) +
                           '亿元；机构披露净额' + fmt(r['institution_net_yuan'] / 1e8) + '亿元；买一占' + fmt((r['top_buy_share'] or 0) * 100) + '%。'
                           for r in focus)
    add('dragon_tiger', '11月6日龙虎榜补做｜沪深57只与全席位、官方对照',
        f'取得沪深71条原因/57只全部买卖席位；{len(exact)}只两侧前五与上交所原文精确一致，深市及科创官方核验尚未齐。',
        f'原来源总表78条/62只含北交所，本研究排除北交所后为71条/57只。每只BUY/SELL均实际返回；'
        f'逐原因保留TRADE_ID，展示优先单日，没有把单日与多日加总。独立金股页面金额核对通过{sum(r["aijingu_amount_crosscheck"] for r in seat_records)}/57只。\n\n' +
        seat_table + '\n\n重点观察与风险对照（不是按净买额机械荐股）：\n\n' + focus_text +
        '\n\n上海电影的机构买与股通卖须同时看，不能只摘录买方；百洋买一集中度高，披露净买较大也带来单一分支依赖；'
        '东方日升与智动力为20%制度股票，日内修复与次日溢价不能和10%主板直接混排；冰山冷热负反馈作失败对照。'
        '机构专用与营业部均只是披露标签，不能确认账户身份、锁仓或做T。'
        '机构净额按同TRADE_ID去重披露行计算，不等于全市场主力资金。\n\n'
        '上交所原接口返回正确交易日和完整主板文本；深交所请求仅空metadata，不视为原表成功；科创原表未补齐。'
        '因此仍为partial，继续核对深市/科创原始席位、历史画像、逐时板块和次日执行，不升级为完整前置。',
        sources=[raw_lhb['main_list']['source'], exchange['sse']['source'], exchange['szse']['source'], exchange['aijingu']['source']])
    add('learning_review', '11月6日学习复核补做｜分开比较上涨比例与收益',
        '已复核11月6日31条学习记录、17证券基准日/8日期，拆分成功率与收益目标；真实成交与净收益均未知，未自动调权。',
        '本轮独立学习分析完成，不表示上游六项研究完成。使用forward-learning-2026-11-06真实快照；31条原记录，'
        '22条可观察、9条回顾性不合格，按证券+实际价格基准日去重17事件/8日期，重复同证券仍相关。\n\n' + horizon_table +
        '\n\n涨得更经常和赚得更多分别研究。原低位结构4只/1日期，T+5正比例75%但均值-0.958%，'
        '平均正变动1.402%、唯一负变动-8.040%；一次大亏可吞掉多次小涨。T+10正比例25%、均值-1.623%。'
        '这只支持小样本内对照，不证明长期负或正期望。当前总样本T+5/T+10更差，不能把持有更久当解套方案。\n\n'
        '两个时段分别读取原生产intraday-performance及dual_objective_research；按时段、版本、基准日、T+1/T+2/T+5/T+10分组，'
        '不把10月29日旧版本和11月6日新版本混为同组。以下是全部已返回分组，不挑有利时段：\n\n' + intraday_table +
        '\n\n11月6日周五冻结的T+1要11月9日收盘才成熟，不能周末提前算收益。'
        '早尾盘原各2只留存，不补造买单。\n\n'
        '下一轮预注册假设：H1低位适度放量+收盘站回关键均线，与高量低CLV分别比较；H2突破后缩量回踩与直接追高分别比较；'
        'H3逐时板块同步能否减少假突破。冻结版本、保留亏损/未触发/不可成交样本，以平均/中位、平均盈亏、尾部MAE和样本日期数共同评估。'
        '36证券日/20独立日期下限未达到，不宣称统计优势。真实交易胜率、扣成本净收益和盘口可执行性留空。'
        '本轮没有自动训练或修改选股权重。', status='completed', full=True,
        sources=['https://robin-stock-api-production.up.railway.app/api/learning',
                 'https://robin-stock-api-production.up.railway.app/api/strategy-lab',
                 'https://robin-stock-api-production.up.railway.app/api/intraday-performance?slot=early_pair',
                 'https://robin-stock-api-production.up.railway.app/api/intraday-performance?slot=late_pair'])
    add('limitup_single', '11月6日独立打板补做｜周一条件预案与否决证据',
        '独立核对T日涨停生态和20%/10%风险；下周一60秒承接、竞价及封单无原时点证据，正式打板0只。',
        'T日原复盘记录、当前沪深收盘和龙虎榜一起作为背景；涨停价计算代理不是交易所证券状态校验，不把ST及新股无涨跌幅日混入普通主板。'
        '上海电影、华升股份等已封板仅作为板后承接对照；东方日升+15.26%不是20%涨停，不能称封板；智动力20%与普通主板分开。\n\n'
        'D=11月9日先核证券状态、当日真实涨停价、竞价、同伴与高标负反馈，再观察09:35—10:30首次分歧、至少60秒连续承接和回封；'
        '一字排队、板块转弱、无连续盘口或盘口时间戳不新鲜均放弃。五分钟能检验形态，却不能证明60秒承接和排队成交。'
        '当前没有D实际原时点数据，正式候选0只，净收益/真实胜率N/A；不因空仓取消形态研究，也不预填成交。'
        '后续必须由原时点采集检查条件。若11月9日买入，11月10日才可卖；触发失效也不能当天卖。')
    pair_table = table(['沿用待综合观察', 'T收盘参考', '原冻结', '已补证/仍缺'], [
        [r['code'] + ' ' + r['name'], fmt(r['reference_price'], 2), r['actual_frozen_at'],
         '48根五分钟核对完成；公告/完整行业/正式综合仍缺'] for r in waiting_pair])
    add('combined_pair', '11月6日综合补做｜完整输入检查与两只待综合观察',
        '已读全部同T报告并在学习/独立打板之后重评，保留两只原量价待综合观察；前置仍partial，尚未形成最终双标。',
        '输入按顺序读取：market-review-20261106-partial-v1、volume-price-20261106-partial-v1与本轮28分钟补证、'
        + PREFIX + '-low_position-v1、' + PREFIX + '-dragon_tiger-v1、' + PREFIX + '-learning_review-v1、' + PREFIX + '-limitup_single-v1。'
        '学习和独立打板先归档，再形成此比较；市场/量价/低位/龙虎榜完整门禁仍未通过。\n\n' + pair_table +
        '\n\n东方环宇相较未复MA60的乐山电力更接近价格突破，华银电力保留低位置修复比较；'
        '海源复材、中利集团放量低收盘位置排在后面，东方电热较长上影削弱推进质量。'
        '这只是对原量价观察的追加审查，不能把预选改名为最终综合。两只原冻结时间保持，不新增收益样本或正式recommendations。'
        '原观察条件继续保留：华银先观察回踩不破T日中枢、电力同步后再站回6.19，跌破5.55或放量冲高回落放弃；'
        '东方环宇先观察回踩17.94前高、燃气同步后再核18.75上方成交，跌破16.99或突破背离放弃。'
        '上述条件仅为旧研究假设，D日须另核新鲜原时点报价及隔夜风险；没有成交证据不能填入买入。'
        '最终比较仍需完整公告/行业和龙虎榜原表输入；正式买点与研究观察分开，不把等候状态称完成。',
        status='waiting', research_shadow_candidates=waiting_pair)
    research['items'].extend(reports)
    write('backend/data/research.json', research)
    write('backend/data/task_runs.json', runs)

    # Reflect the confirmed merged scheduler without publishing private IDs/prompts.
    tasks = read('backend/data/tasks.json')
    registry = {r['id']: r for r in tasks['items']}
    registry['learning_review'].update(title='每日学习复核＋周日研究总结',
        schedule_text='奥克兰周二至周六08:00每日学习与查漏；周日08:00每周研究总结，共用一个外部调度。',
        schedule='BEGIN:VEVENT\nDTSTART;TZID=Pacific/Auckland:20261108T080000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH,FR,SA,SU;BYHOUR=8;BYMINUTE=0;BYSECOND=0\nEND:VEVENT',
        execution_mode='external_scheduled_learning_and_weekly_review', configuration_confirmed_at=stamp)
    registry['weekly_review'].update(schedule_text='奥克兰周日08:00，由每日学习复核共用调度执行；不暂停量价。',
        enabled=True, effective_enabled=True, independent_schedule_enabled=False,
        executor_task_id='learning_review', execution_mode='merged_learning_review_weekly_component',
        configuration_confirmed_at=stamp)
    registry['volume_price'].update(enabled=True, effective_enabled=True, configuration_confirmed_at=stamp)
    tasks['updated_at'] = stamp
    write('backend/data/tasks.json', tasks)
    current_doc = ROOT / 'docs/current-execution.md'
    current_doc.write_text('# 2026-11-07：恢复五项常驻合并安排\n\n'
        '每日学习复核共用奥克兰周二至周日08:00：周二至周六执行每日学习与跨日补做，周日执行周总结。'
        '每日复盘保留工作日21:44与周六APP自主打磨。独立周报调度停用；量价持续启用，取消周末暂停/切换/恢复逻辑。'
        '低位/龙虎榜、量价与最终综合原时间保持。综合仍在08:00学习之后09:00，独立打板先归档，最后综合评比。'
        'tasks.json中的weekly_review为合并组件，不占独立外部任务。研究缺项不因合并消失。\n\n' + current_doc.read_text())
    print(json.dumps({'reports': [r['id'] for r in reports], 'learning_completed': True,
                      'verified_minutes': 28, 'old_low_paths': len(low_paths), 'lhb_codes': 57,
                      'official_exact_codes': len(exact), 'vendor_amount_crosschecked': sum(r['aijingu_amount_crosscheck'] for r in seat_records),
                      'final_pair_completed': False, 'timestamp': stamp}, ensure_ascii=False))


if __name__ == '__main__':
    main()
