import unittest
from lhb_official import parse_star, primary_urls, broker_seat_union


class OfficialDisclosureTests(unittest.TestCase):
    def test_generic_institution_code_does_not_overwrite_other_seat(self):
        rows = [dict(TRADE_ID='r', OPERATEDEPT_CODE='generic', OPERATEDEPT_NAME='机构专用', BUY=0, SELL=v)
                for v in [100, 200]]
        result = broker_seat_union(rows, rows, 'r')
        self.assertEqual(result['institution_net'], -300)

    def test_sell_column_and_period_are_independent_of_buy_column(self):
        buy = [dict(TRADE_ID='r', OPERATEDEPT_NAME='甲', BUY=10, SELL=2),
               dict(TRADE_ID='other-period', OPERATEDEPT_NAME='甲', BUY=1000, SELL=0)]
        sell = [dict(TRADE_ID='r', OPERATEDEPT_NAME='乙', BUY=3, SELL=20)]
        result = broker_seat_union(buy, sell, 'r')
        self.assertEqual(result['buy'], 13)
        self.assertEqual(result['sell'], 22)
        self.assertEqual(result['net'], -9)

    def test_duplicate_anonymous_rows_in_same_side_are_not_collapsed(self):
        row = dict(TRADE_ID='r', OPERATEDEPT_NAME='机构专用', BUY=0, SELL=100)
        self.assertEqual(broker_seat_union([row, row], [row], 'r')['sell'], 200)

    def test_STAR_uses_separate_endpoint_and_szse_current_catalog(self):
        urls = primary_urls('2026-11-18')
        self.assertIn('queryKCBTradeInfo.do?tradeDate=20261118', urls['sse_star'])
        self.assertIn('1842_xxpl', urls['szse_first_page'])

    def test_wanyuan_converted_without_mixing_opposite_sides(self):
        row = {'secCode': '688001', 'refType': '1', 'tradeDate': '20261118',
               'deptNameB': '买方', 'deptTxAmtB': '1.23',
               'deptNameS': '卖方', 'deptTxAmtS': '4.56'}
        actual = parse_star({'pageHelp': {'data': [row]}}, '2026-11-18')[0]
        self.assertEqual(actual['buy'][0]['amount_yuan'], 12300)
        self.assertEqual(actual['sell'][0]['amount_yuan'], 45600)

    def test_nested_investor_categories_never_become_top_five_seats(self):
        row = {'secCode': '688001', 'refType': '12', 'tradeDate': '20261118',
               'A00': {'investorDesc': '自然人', 'investorTxAmtB': '100'},
               'A10': {'investorDesc': '中小投资者', 'investorTxAmtB': '60'}}
        actual = parse_star({'pageHelp': {'data': [row]}}, '2026-11-18')[0]
        self.assertEqual(actual['kind'], 'investor_categories')
        self.assertIsNone(actual['seat_net_yuan'])
        self.assertNotIn('buy', actual)

    def test_HTTP_success_with_wrong_date_or_missing_data_is_rejected(self):
        for payload in [{}, {'pageHelp': {'data': [{'tradeDate': '20261117'}]}}]:
            with self.assertRaises(ValueError):
                parse_star(payload, '2026-11-18')
