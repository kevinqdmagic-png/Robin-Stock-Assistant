# 龙虎榜原始证据契约

2026-11-18本轮已实测：上交所主板与科创板不是同一接口。

- 主板：`infodisplay/showTradePublicFile.do?dateTx=YYYY-MM-DD`；前五席位金额为元。
- 科创板：`marketdata/tradedata/queryKCBTradeInfo.do?tradeDate=YYYYMMDD`。依据上交所自己的`/xhtml/star/js/search/search_jygkxx.js`；`deptTxAmtB/S`单位为万元，转元时乘10000。每席四舍五入最大50元，五席合计核对容差250元。证券、披露日与区间仍须一致。
- 深交所：`CATALOGID=1842_xxpl`，按返回pagecount取完整分页，再沿原文a-param取得`1842_detal`；明细mrje/mcje为元。`1802_xxpl`返回HTTP200及空数据不算取证成功。
- 科创板严重异常披露的A00自然人包含A10/A20等子类；D00机构也不是“机构专用”席位。分类统计不能当五席位相加，不计算席位净额/集中度。
- 东财每个TRADE_ID先独立处理；同一区间相同席位的不同上榜原因只计一次。买卖榜并集要去重，且包含买榜中的卖出、卖榜中的买入，不能用卖榜BUY字段充当卖出金额。不同披露区间不叠加成当日资金。

`backend/lhb_official.py`提供日期、单位和披露类型解析；对应回归覆盖万元换算、错误日期、空载荷与嵌套分类。正文研究及交易资格仍按原方法，不能以接口成功替代完整研究。

普通席位并集使用`broker_seat_union`按TRADE_ID处理：只消除两侧重复出现的相同披露行，不以通用机构代码覆盖另一笔不同金额的匿名机构席位；同一侧相同名称/金额的多行也不擅自合并成同一账户。买卖分别使用BUY/SELL列，三日与单日不相加。2026-11-13和林微纳原机构、股通净额的覆盖错误已另行追加历史纠错，不改旧记录。
