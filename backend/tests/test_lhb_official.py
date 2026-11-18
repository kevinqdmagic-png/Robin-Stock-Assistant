import unittest
from lhb_official import parse_star, primary_urls


class OfficialDisclosureTests(unittest.TestCase):
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
