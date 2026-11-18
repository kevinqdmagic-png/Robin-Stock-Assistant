"""Source contracts for SSE STAR disclosures: CNY 10,000 and nested categories."""
from datetime import date
from decimal import Decimal
from collections import Counter


def broker_seat_union(buy_rows, sell_rows, trade_id):
    """Combine one reason/period; retain distinct anonymous institution rows."""
    sides = [[r for r in rows if str(r.get('TRADE_ID')) == str(trade_id)]
             for rows in (buy_rows, sell_rows)]
    if not all(sides):
        raise ValueError('missing_disclosure_side')
    def key(row):
        return (row['OPERATEDEPT_NAME'], float(row.get('BUY') or 0), float(row.get('SELL') or 0))
    rows = list(sides[0])
    overlap = Counter(key(r) for r in sides[0])
    for row in sides[1]:
        k = key(row)
        if overlap[k]:
            overlap[k] -= 1
        else:
            rows.append(row)
    if any(r['OPERATEDEPT_NAME'] in {'自然人', '其他自然人', '中小投资者', '机构'} for r in rows):
        raise ValueError('investor_categories_are_not_broker_seats')
    buy = sum(float(r.get('BUY') or 0) for r in rows)
    sell = sum(float(r.get('SELL') or 0) for r in rows)
    return {'buy': buy, 'sell': sell, 'net': buy - sell,
            'institution_net': sum(float(r.get('BUY') or 0) - float(r.get('SELL') or 0)
                                   for r in rows if r['OPERATEDEPT_NAME'] == '机构专用'),
            'connect_net': sum(float(r.get('BUY') or 0) - float(r.get('SELL') or 0)
                              for r in rows if '股通' in r['OPERATEDEPT_NAME'])}


def primary_urls(day):
    day = date.fromisoformat(day).isoformat()
    return {
        'sse_main': 'https://query.sse.com.cn/infodisplay/showTradePublicFile.do?isPagination=false&dateTx=' + day,
        'sse_star': 'https://query.sse.com.cn/marketdata/tradedata/queryKCBTradeInfo.do?tradeDate=' + day.replace('-', ''),
        'szse_first_page': 'https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1842_xxpl&txtStart=' + day + '&txtEnd=' + day + '&tab1PAGENO=1',
    }


def parse_star(payload, day):
    expected = date.fromisoformat(day).strftime('%Y%m%d')
    rows = payload.get('pageHelp', {}).get('data')
    if not isinstance(rows, list):
        raise ValueError('missing_STAR_disclosure_payload')
    result = []
    for row in rows:
        if row.get('tradeDate') != expected:
            raise ValueError('STAR_disclosure_date_mismatch')
        out = {'code': row['secCode'], 'ref_type': row['refType'],
               'start_date': row.get('unnormalStartDate'), 'end_date': row.get('unnormalEndDate')}
        if row.get('deptTxAmtB') and row.get('deptTxAmtS'):
            out['kind'] = 'broker_seats'
            for suffix, side in [('B', 'buy'), ('S', 'sell')]:
                names = row['deptName' + suffix].split(',')
                values = row['deptTxAmt' + suffix].split(',')
                if len(names) != len(values):
                    raise ValueError('STAR_seat_columns_mismatch')
                out[side] = [{'name': n, 'amount_yuan': float(Decimal(v) * 10000)}
                             for n, v in zip(names, values)]
        else:
            categories = {k: v for k, v in row.items()
                          if isinstance(v, dict) and 'investorDesc' in v}
            if not categories:
                raise ValueError('unrecognized_STAR_disclosure')
            # A10/A20 are children of A00. Never add the hierarchy into seats.
            out.update(kind='investor_categories', categories=categories,
                       seat_net_yuan=None, institution_seat_net_yuan=None)
        result.append(out)
    return result
