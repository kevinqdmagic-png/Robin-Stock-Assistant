"""Source contracts for SSE STAR disclosures: CNY 10,000 and nested categories."""
from datetime import date
from decimal import Decimal


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
