package com.robin.stock

import android.graphics.*
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private val base = "https://robin-stock-api-production.up.railway.app"
    private val prefs by lazy { getSharedPreferences("robin", MODE_PRIVATE) }
    private val executor = Executors.newFixedThreadPool(3)
    private val homeRefreshHandler = Handler(Looper.getMainLooper())
    private val autoRefreshMs = 30_000L
    private val red = Color.rgb(218, 45, 61)
    private val green = Color.rgb(20, 143, 102)
    private var overviewBox: LinearLayout? = null
    private var sectorBox: LinearLayout? = null
    private var overviewData: JSONObject? = null
    private var sectorKind = "industry"
    private var homeIsLive = false
    private var refreshTick = 0
    private val ink = Color.rgb(35, 38, 44)
    private val muted = Color.rgb(122, 126, 134)
    private lateinit var root: LinearLayout
    private lateinit var scroller: ScrollView
    private lateinit var nav: LinearLayout
    private var currentTab = 0
    private var pageGeneration = 0
    private var minuteGeneration = 0
    private var selectedCode = ""
    private var isForeground = false
    private var homeRefreshTask: Runnable? = null
    private var homeMarketStatus: TextView? = null
    private var homeCandidatesBox: LinearLayout? = null
    private val validCode = Regex("[0-9]{6}")
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
    private fun label(value: String, size: Float = 15f, bold: Boolean = false) = TextView(this).apply {
        text = value; textSize = size; setTextColor(if (bold) ink else muted)
        setPadding(0, dp(5), 0, dp(5))
        if (bold) setTypeface(typeface, Typeface.BOLD)
    }
    private fun surface(color: Int, radius: Int = 16) = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(radius).toFloat()
    }
    private fun card(title: String) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(12), dp(16), dp(14))
        background = surface(Color.WHITE)
        root.addView(this, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(12) })
        if (title.isNotEmpty()) addView(label(title, 19f, true))
    }
    private fun action(title: String, click: () -> Unit) = Button(this).apply {
        text = title; textSize = 14f; isAllCaps = false; setTextColor(red)
        backgroundTintList = android.content.res.ColorStateList.valueOf(Color.rgb(255, 241, 242))
        setOnClickListener { click() }
    }
    private fun codeInput() = EditText(this).apply {
        hint = "输入六位股票代码"; textSize = 16f; isSingleLine = true
        inputType = android.text.InputType.TYPE_CLASS_NUMBER
        filters = arrayOf(android.text.InputFilter.LengthFilter(6))
    }
    private fun checked(input: EditText, run: (String) -> Unit) {
        val code = input.text.toString().trim()
        if (validCode.matches(code)) run(code) else input.error = "请输入六位股票代码"
    }
    private fun watchCodes(): List<String> {
        val saved = prefs.getString("watchlist", null)
        return (saved ?: prefs.getString("watch", "").orEmpty()).split(",").filter { validCode.matches(it) }.distinct()
    }
    private fun saveWatch(code: String) {
        prefs.edit().putString("watchlist", (watchCodes() + code).distinct().joinToString(",")).apply()
        Toast.makeText(this, "已加入自选", Toast.LENGTH_SHORT).show()
    }
    private fun request(path: String): JSONObject {
        val conn = URL(base + path).openConnection() as HttpURLConnection
        conn.connectTimeout = 12000; conn.readTimeout = 25000
        try {
            if (conn.responseCode !in 200..299) error("HTTP ${conn.responseCode}")
            return JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
        } finally { conn.disconnect() }
    }
    private fun fetch(path: String, result: (JSONObject?, String?) -> Unit) {
        val generation = pageGeneration
        executor.execute {
            val data = runCatching {
                request(path).also {
                    if (it.optBoolean("ok") && (path.startsWith("/api/research") || path == "/api/recommendations?limit=12"))
                        prefs.edit().putString("cache:$path", it.toString()).apply()
                }
            }.recoverCatching {
                val cached = prefs.getString("cache:$path", null) ?: throw it
                JSONObject(cached).put("_offline", true)
            }
            runOnUiThread {
                if (!isDestroyed && generation == pageGeneration) result(data.getOrNull(), data.exceptionOrNull()?.message)
            }
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        selectedCode = savedInstanceState?.getString("code") ?: prefs.getString("selected", prefs.getString("watch", "")).orEmpty()
        val shell = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Color.rgb(245, 247, 250)) }
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(12), dp(16), dp(16)) }
        scroller = ScrollView(this).apply { isFillViewport = true; addView(root) }
        shell.addView(scroller, LinearLayout.LayoutParams(-1, 0, 1f))
        nav = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setBackgroundColor(Color.WHITE); elevation = dp(5).toFloat() }
        shell.addView(nav, LinearLayout.LayoutParams(-1, -2))
        setContentView(shell)
        ViewCompat.setOnApplyWindowInsetsListener(shell) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom); insets
        }
        showTab(savedInstanceState?.getInt("tab") ?: 0)
    }
    override fun onSaveInstanceState(outState: Bundle) {
        outState.putInt("tab", currentTab); outState.putString("code", selectedCode); super.onSaveInstanceState(outState)
    }
    override fun onResume() {
        super.onResume()
        isForeground = true
        if (currentTab == 0) overviewBox?.let { loadOverview(it) }
        startHomeAutoRefresh()
    }
    override fun onPause() {
        isForeground = false
        stopHomeAutoRefresh()
        super.onPause()
    }
    override fun onDestroy() {
        stopHomeAutoRefresh()
        executor.shutdownNow()
        super.onDestroy()
    }
    @Deprecated("Legacy back handling")
    override fun onBackPressed() { if (currentTab != 0) showTab(0) else super.onBackPressed() }
    private fun showTab(index: Int) {
        stopHomeAutoRefresh()
        homeMarketStatus = null
        homeCandidatesBox = null
        overviewBox = null
        sectorBox = null
        currentTab = index; pageGeneration++; root.removeAllViews(); nav.removeAllViews(); scroller.scrollTo(0, 0)
        val tabs = listOf("首页", "自选", "分时", "股票研究")
        tabs.forEachIndexed { i, title ->
            val item = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER; setPadding(dp(2), dp(9), dp(2), dp(8))
                contentDescription = title; isSelected = i == index
                addView(NavIcon(i, if (i == index) red else muted), LinearLayout.LayoutParams(dp(24), dp(24)))
                addView(label(title, 12f, i == index).apply { setTextColor(if (i == index) red else muted); gravity = Gravity.CENTER })
                setOnClickListener { if (currentTab != i) showTab(i) }
            }
            nav.addView(item, LinearLayout.LayoutParams(0, -2, 1f))
        }
        root.addView(label(if (index == 0) "Robin 股票助手" else tabs[index], 26f, true))
        root.addView(label(when(index) { 0 -> "看市场 · 等确认 · 留记录"; 1 -> "我的关注 · 保存在本机"; 2 -> "分钟走势 · 北京时间"; else -> "研究留档 · 推荐跟踪 · 历史验证" }, 13f).apply { setPadding(0, 0, 0, dp(18)) })
        when (index) { 0 -> home(); 1 -> watchlist(); 2 -> minuteCard(); else -> research() }
    }
    private fun pctText(value: Double): String =
        if (!value.isFinite()) "—" else String.format(java.util.Locale.CHINA, "%+.2f%%", value)
    private fun numText(value: Double, digits: Int = 2): String =
        if (!value.isFinite()) "—" else String.format(java.util.Locale.CHINA, "%.${digits}f", value)
    private fun trendColor(value: Double) = if (!value.isFinite() || value == 0.0) muted else if (value > 0) red else green
    private fun textRow(parent: LinearLayout, left: String, right: String, pct: Double = Double.NaN) {
        val row = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(7), 0, dp(7)) }
        row.addView(label(left, 14f, true), LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(label(right, 14f, true).apply { setTextColor(trendColor(pct)); gravity = Gravity.END })
        parent.addView(row)
    }
    private fun home() {
        val market = card("市场概览")
        val status = label("正在读取行情…", 12f); market.addView(status)
        val indices = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }; market.addView(indices)
        val candidates = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        homeMarketStatus = status; homeCandidatesBox = candidates; overviewBox = indices
        market.addView(action("刷新市场") { loadMarket(status, candidates); loadOverview(indices) })
        val sectors = card("板块强弱")
        val switcher = LinearLayout(this)
        switcher.addView(action("行业板块") { sectorKind = "industry"; renderSectors() }, LinearLayout.LayoutParams(0, -2, 1f))
        switcher.addView(action("概念板块") { sectorKind = "concept"; renderSectors() }, LinearLayout.LayoutParams(0, -2, 1f))
        sectors.addView(switcher)
        val sectorItems = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        sectors.addView(sectorItems); sectorItems.addView(label("正在读取板块…", 12f)); sectorBox = sectorItems
        val signalCard = card("买点观察")
        val signalStatus = label("正在扫描观察信号…", 16f, true)
        val signalItems = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        signalCard.addView(signalStatus)
        signalCard.addView(label("低位首次启动 · 分歧转一致 · 超跌转强", 12f))
        signalCard.addView(signalItems)
        signalCard.addView(action("刷新买点观察") { loadSignals(signalStatus, signalItems) })
        val pool = card("动态候选")
        pool.addView(label("全市场入口 · 量价初筛 · 点击查看分时", 12f)); pool.addView(candidates)
        loadMarket(status, candidates); loadOverview(indices); loadSignals(signalStatus, signalItems)
        startHomeAutoRefresh()
    }
    private fun loadOverview(box: LinearLayout) {
        fetch("/api/overview") { data, _ ->
            if (data == null || !data.optBoolean("ok")) {
                if (box.childCount == 0) box.addView(label("指数与板块暂不可用，点击刷新重试。", 12f))
                sectorBox?.let { if (it.childCount <= 1) { it.removeAllViews(); it.addView(label("板块数据暂不可用", 12f)) } }
                return@fetch
            }
            overviewData = data; homeIsLive = data.optJSONObject("session")?.optBoolean("is_live") == true
            box.removeAllViews()
            box.addView(label(data.optJSONObject("session")?.optString("label").orEmpty() +
                if (data.optBoolean("stale")) " · 缓存已过期" else if (!homeIsLive) " · 显示最近可用行情" else " · 候选30秒刷新", 12f))
            val rows = data.optJSONArray("indices") ?: JSONArray()
            val byCode = (0 until rows.length()).mapNotNull { rows.optJSONObject(it) }.associateBy { it.optString("code") }
            val ordered = listOf("000001", "399001", "399006", "000300").mapNotNull { byCode[it] }
            for (start in ordered.indices step 2) {
                val row = LinearLayout(this)
                ordered.drop(start).take(2).forEach { x ->
                    val tile = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(6), dp(8), dp(8)) }
                    val pct = x.optDouble("pct")
                    tile.addView(label(x.optString("name"), 12f))
                    tile.addView(label(numText(x.optDouble("price")), 21f, true).apply { setTextColor(trendColor(pct)) })
                    tile.addView(label(pctText(pct), 13f, true).apply { setTextColor(trendColor(pct)) })
                    row.addView(tile, LinearLayout.LayoutParams(0, -2, 1f))
                }
                box.addView(row)
            }
            val times = ordered.map { it.optString("as_of").takeIf { time -> time.isNotBlank() && time != "null" } }
            val time = times.filterNotNull().minOrNull()
            box.addView(label("指数数据：${time ?: "时间待核验"} · 北京时间", 11f))
            if (data.optString("status") == "partial") box.addView(label("部分指数或板块暂不可用，已保留可用部分。", 11f))
            renderSectors()
        }
    }
    private fun renderSectors() {
        val box = sectorBox ?: return
        box.removeAllViews()
        val board = overviewData?.optJSONObject(sectorKind)
        val kindLabel = if (sectorKind == "industry") "行业" else "概念"
        var count = 0
        for (side in listOf("strong", "weak")) {
            val rows = board?.optJSONArray(side) ?: JSONArray()
            box.addView(label("$kindLabel · " + if (side == "strong") "领涨" else "领跌", 12f, true))
            for (i in 0 until minOf(3, rows.length())) {
                val x = rows.optJSONObject(i) ?: continue
                val pct = x.optDouble("pct")
                textRow(box, x.optString("name"), pctText(pct), pct)
                val leader = x.optString("leader").takeIf { it.isNotBlank() && it != "null" }
                if (side == "strong" && leader != null)
                    box.addView(label("领涨股 $leader · ${pctText(x.optDouble("leader_pct"))}", 11f))
                count++
            }
        }
        if (count == 0) box.addView(label("当前板块数据暂不可用，请刷新市场。", 12f))
        box.addView(label("板块可重叠，涨跌幅不能相加；来源：东方财富公开行情。", 11f))
    }

    private fun startHomeAutoRefresh() {
        stopHomeAutoRefresh()
        if (!isForeground || currentTab != 0) return
        val task = object : Runnable {
            override fun run() {
                if (!isForeground || currentTab != 0) return
                val status = homeMarketStatus ?: return
                val box = homeCandidatesBox ?: return
                if (homeIsLive) {
                    loadLiveCandidates(box)
                    if (++refreshTick % 3 == 0) {
                        loadMarket(status, box)
                        overviewBox?.let { loadOverview(it) }
                    }
                }
                homeRefreshHandler.postDelayed(this, autoRefreshMs)
            }
        }
        homeRefreshTask = task
        homeRefreshHandler.postDelayed(task, autoRefreshMs)
    }

    private fun stopHomeAutoRefresh() {
        homeRefreshTask?.let { homeRefreshHandler.removeCallbacks(it) }
        homeRefreshTask = null
    }
    private fun watchlist() {
        card("添加自选").apply {
            val input = codeInput(); addView(input)
            addView(action("加入自选") { checked(input) { saveWatch(it); showTab(1) } })
        }
        val codes = watchCodes()
        if (codes.isEmpty()) card("").addView(label("还没有自选股。输入代码添加，或在分时页点击加入自选。"))
        codes.forEach { code ->
            card("").apply {
                addView(label(code, 20f, true))
                val row = LinearLayout(this@MainActivity)
                row.addView(action("查看分时") { selectedCode = code; showTab(2) }, LinearLayout.LayoutParams(0, -2, 1f))
                row.addView(action("移除") {
                    prefs.edit().putString("watchlist", watchCodes().filter { it != code }.joinToString(",")).apply(); showTab(1)
                }, LinearLayout.LayoutParams(0, -2, 1f))
                addView(row)
            }
        }
    }
    private fun minuteCard() {
        val minute = card("个股分时")
        val title = label("选择股票查看走势", 17f, true); minute.addView(title)
        val input = codeInput(); input.setText(selectedCode); minute.addView(input)
        val status = label("输入代码，或从自选和动态候选进入。", 12f)
        val chart = MinuteChart()
        val row = LinearLayout(this)
        fun load(code: String) {
            selectedCode = code; prefs.edit().putString("selected", code).apply()
            title.text = "$code · 分时"; status.text = "正在读取分钟数据…"; chart.setBars(JSONArray())
            val requestId = ++minuteGeneration
            fetch("/api/stocks/$code/minute") { data, error ->
                if (requestId != minuteGeneration) return@fetch
                val bars = data?.optJSONArray("bars") ?: JSONArray()
                if (data == null || !data.optBoolean("ok") || bars.length() == 0) {
                    status.text = "分时暂不可用，请稍后刷新。" + (error?.let { "\n$it" } ?: "")
                } else {
                    chart.setBars(bars)
                    status.text = "最后数据：${bars.optJSONObject(bars.length()-1)?.optString("time")}\n收盘后显示历史走势；当前为手动刷新。"
                }
            }
        }
        row.addView(action("查看 / 刷新") { checked(input) { load(it) } }, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(action("加入自选") { checked(input) { saveWatch(it) } }, LinearLayout.LayoutParams(0, -2, 1f))
        minute.addView(row); minute.addView(status); minute.addView(chart, LinearLayout.LayoutParams(-1, dp(if (currentTab == 0) 220 else 320)))
        if (validCode.matches(selectedCode)) load(selectedCode)
    }
    private fun loadSignals(status: TextView, box: LinearLayout) {
        status.text = "正在扫描观察信号…"
        box.removeAllViews()
        fetch("/api/signals?limit=8") { data, error ->
            box.removeAllViews()
            if (data == null || !data.optBoolean("ok")) {
                status.text = "信号扫描暂不可用，请稍后刷新。"
                box.addView(label(error ?: "后台正在准备分钟数据。", 12f))
                return@fetch
            }
            val rows = data.optJSONArray("signals") ?: JSONArray()
            val time = data.optString("time_cn")
            if (rows.length() == 0) {
                status.text = "当前暂无符合条件的观察信号"
                box.addView(label("模型已接通 · 扫描 ${data.optInt("scanned")} 只候选 · $time", 12f))
                box.addView(label("没有信号时保持观察；当前模型尚未回测，不把“无信号”当故障。", 12f))
                return@fetch
            }
            status.text = "发现 ${rows.length()} 个观察信号 · $time"
            for (i in 0 until rows.length()) {
                val x = rows.getJSONObject(i)
                val code = x.optString("code").takeLast(6)
                val reasons = x.optJSONArray("reasons")
                val reasonText = if (reasons != null) {
                    (0 until reasons.length()).joinToString(" · ") { reasons.optString(it) }
                } else ""
                val text = buildString {
                    append("${x.optString("state")}  ${x.optString("name")}  $code\n")
                    append("${x.optString("type")} · 强度 ${x.optInt("score")}/100")
                    append(" · ${x.optString("pct")}%\n")
                    append("现价 ¥${x.optString("price")}  ·  确认 ¥${x.optString("confirm_price")}  ·  失效 ¥${x.optString("invalid_price")}")
                    if (reasonText.isNotBlank()) append("\n$reasonText")
                }
                box.addView(label(text, 14f).apply {
                    setTextColor(ink)
                    setPadding(0, dp(12), 0, dp(12))
                    setOnClickListener { selectedCode = code; showTab(2) }
                })
            }
            box.addView(label("试运行信号：先接通并记录，完成样本积累后再做回测与阈值校准。", 12f))
        }
    }

    private fun renderCandidates(box: LinearLayout, rows: JSONArray, updatedAt: String? = null) {
        box.removeAllViews()
        if (!updatedAt.isNullOrBlank()) box.addView(label("读取时间 $updatedAt · 北京时间", 11f))
        if (rows.length() == 0) box.addView(label("当前没有可用候选", 13f))
        for (i in 0 until minOf(20, rows.length())) {
            val x = rows.getJSONObject(i); val code = x.optString("code").takeLast(6)
            val item = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL; setPadding(0, dp(8), 0, dp(10))
                setOnClickListener { selectedCode = code; showTab(2) }
            }
            val pct = x.optDouble("pct")
            textRow(item, "${x.optString("name")}  $code", pctText(pct), pct)
            item.addView(label("¥${numText(x.optDouble("price"))}  ·  量比 ${numText(x.optDouble("volume_ratio"))}  ·  换手 ${numText(x.optDouble("turnover"))}%", 12f))
            box.addView(item)
        }
    }
    private fun loadLiveCandidates(box: LinearLayout) {
        fetch("/api/candidates?limit=20") { data, _ ->
            if (data == null || !data.optBoolean("ok")) {
                homeMarketStatus?.text = "候选刷新失败，仍显示上次结果；请稍后重试。"
                return@fetch
            }
            renderCandidates(box, data.optJSONArray("candidates") ?: JSONArray(), data.optString("time_cn"))
            if (data.optString("status") == "fallback_market_cache")
                box.addView(label("备用缓存 · ${data.optInt("cache_age_sec")} 秒前，请核对数据时间。", 11f))
        }
    }
    private fun loadMarket(status: TextView, box: LinearLayout) {
        if (box.childCount == 0) status.text = "正在读取市场行情…"
        fetch("/api/market") { data, error ->
            if (data == null || !data.optBoolean("ok")) {
                status.text = "市场行情暂不可用，请刷新重试。" + (error?.let { "\n$it" } ?: ""); return@fetch
            }
            val complete = data.optBoolean("breadth_complete")
            status.text = "上涨 ${data.optInt("advance")}  ·  下跌 ${data.optInt("decline")}  ·  平盘 ${data.optInt("flat")}\n" +
                "${if (complete) "覆盖" else "部分覆盖"} ${data.optInt("count")} 只  ·  " +
                "${data.optString("amount_scope", "覆盖成交额")} ${numText(data.optDouble("amount_yi"))} 亿\n" +
                "读取时间 ${data.optString("time_cn")} · 北京时间" +
                if (data.optBoolean("stale")) "\n缓存已过期，请核对行情时间。" else ""
            renderCandidates(box, data.optJSONArray("candidates") ?: JSONArray(), data.optString("time_cn"))
        }
    }
    private fun research() {
        val names = linkedMapOf("" to "全部", "market_review" to "每日复盘", "volume_price" to "量价研究",
            "dragon_tiger" to "龙虎榜", "low_position" to "低位启动", "quant_research" to "量化研究", "high_elasticity" to "高弹性")
        recommendationCard()
        backtestCard()
        val archive = card("研究历史")
        val day = EditText(this).apply { hint = "按日期查看：2026-09-30"; textSize = 14f; isSingleLine = true }
        archive.addView(day)
        val chips = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        archive.addView(HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(chips) })
        var track = ""; var offset = 0; var requestId = 0
        val status = label("正在读取历史…", 12f); archive.addView(status)
        val items = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }; archive.addView(items)
        val more = action("加载更早记录") { }; more.visibility = View.GONE
        fun load(append: Boolean = false) {
            val filterDate = day.text.toString().trim()
            if (filterDate.isNotBlank() && !Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}").matches(filterDate)) {
                day.error = "日期格式为 YYYY-MM-DD"; return
            }
            if (!append) { offset = 0; items.removeAllViews(); more.visibility = View.GONE }
            val id = ++requestId
            status.text = "正在读取历史…"; more.isEnabled = false
            val path = "/api/research?limit=20&offset=$offset&track=$track&date=$filterDate"
            fetch(path) { data, error ->
                if (id != requestId) return@fetch
                more.isEnabled = true
                if (data == null || !data.optBoolean("ok")) {
                    status.text = "研究档案暂不可用。" + (error?.let { "\n$it" } ?: ""); return@fetch
                }
                val rows = data.optJSONArray("items") ?: JSONArray()
                status.text = (if (data.optBoolean("_offline")) "离线缓存 · " else "") +
                    "共 ${data.optInt("total", rows.length())} 篇 · 点击展开全文"
                if (rows.length() == 0 && !append) items.addView(label("该日期或栏目暂无已归档记录。", 13f))
                for (i in 0 until rows.length()) {
                    val x = rows.getJSONObject(i)
                    val wrapper = LinearLayout(this).apply {
                        orientation = LinearLayout.VERTICAL; setPadding(0, dp(12), 0, dp(16))
                    }
                    wrapper.addView(label("${x.optString("date")} · ${names[x.optString("track")] ?: x.optString("track")}", 12f))
                    wrapper.addView(label(x.optString("title"), 17f, true))
                    wrapper.addView(label(x.optString("summary"), 14f).apply { setTextColor(ink) })
                    val body = label(x.optString("body", x.optString("summary")), 14f).apply {
                        setTextColor(ink); setTextIsSelectable(true); visibility = View.GONE
                    }
                    wrapper.addView(body)
                    val toggle = action("展开全文") { }
                    toggle.setOnClickListener {
                        body.visibility = if (body.visibility == View.VISIBLE) View.GONE else View.VISIBLE
                        toggle.text = if (body.visibility == View.VISIBLE) "收起全文" else "展开全文"
                    }
                    wrapper.addView(toggle)
                    val sources = x.optJSONArray("sources")
                    if (sources != null) for (j in 0 until sources.length()) {
                        val source = sources.optString(j)
                        wrapper.addView(label(source, 11f).apply {
                            setTextIsSelectable(true); autoLinkMask = android.text.util.Linkify.WEB_URLS
                        })
                    }
                    items.addView(wrapper)
                }
                offset += rows.length()
                more.visibility = if (data.optBoolean("has_more")) View.VISIBLE else View.GONE
            }
        }
        names.forEach { (key, title) ->
            chips.addView(action(title) { track = key; load() })
        }
        archive.addView(action("按日期筛选 / 刷新") { load() })
        more.setOnClickListener { load(true) }; archive.addView(more); load()
    }
    private fun recommendationCard() {
        val parent = card("每日双标 · 表现记录")
        parent.addView(label("原始推荐保留，后续结果追加；按交易日跟踪。", 12f))
        val status = label("正在读取推荐记录…", 12f); parent.addView(status)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }; parent.addView(box)
        fetch("/api/recommendations?limit=12") { data, _ ->
            if (data == null || !data.optBoolean("ok")) {
                status.text = "推荐记录暂不可用，请稍后刷新。"; return@fetch
            }
            val rows = data.optJSONArray("items") ?: JSONArray()
            status.text = (if (data.optBoolean("_offline")) "离线缓存 · " else "") + "已归档 ${data.optInt("total", rows.length())} 条"
            if (rows.length() == 0) box.addView(label("历史推荐正在补证。缺少当时价格或时间的记录不计算收益。", 13f))
            val groups = mapOf("close" to "盘后组", "0950" to "早盘9:50", "1440" to "尾盘14:40")
            for (i in 0 until rows.length()) {
                val row = rows.getJSONObject(i)
                val code = row.optString("code")
                box.addView(label("${row.optString("date")} · ${groups[row.optString("group")] ?: row.optString("group")}", 12f))
                box.addView(label("${row.optString("name")}  $code", 16f, true).apply {
                    setOnClickListener { selectedCode = code; showTab(2) }
                })
                box.addView(label(row.optString("reason"), 13f))
                val performance = label("点击查询T+1及3/5/10/20/30交易日表现", 12f); box.addView(performance)
                val check = action("查询后续表现") { }
                check.setOnClickListener {
                    check.isEnabled = false; performance.text = "正在核查后续行情…"
                    val recordId = java.net.URLEncoder.encode(row.optString("id"), "UTF-8")
                    fetch("/api/recommendations/$recordId/performance") { result, _ ->
                        check.isEnabled = true
                        if (result == null || !result.optBoolean("ok")) {
                            performance.text = "后续行情暂不可用。"; return@fetch
                        }
                        val points = result.optJSONArray("points") ?: JSONArray()
                        if (points.length() == 0) {
                            performance.text = result.optString("note", "等待原始记录或后续交易日数据。")
                        } else {
                            performance.text = (0 until points.length()).joinToString("\n") { j ->
                                val p = points.getJSONObject(j)
                                "${p.optInt("horizon")}交易日：" +
                                    if (p.optString("status") == "pending") "等待后续数据"
                                    else "收盘 ${pctText(p.optDouble("close_pct"))} · 最大浮盈 ${pctText(p.optDouble("mfe_pct"))} · 最大不利 ${pctText(p.optDouble("mae_pct"))}"
                            } + "\n" + result.optString("note")
                        }
                    }
                }
                box.addView(check)
            }
            val audit = data.optJSONArray("legacy_audit") ?: JSONArray()
            if (audit.length() > 0) box.addView(label("待补证历史关注："+
                (0 until audit.length()).joinToString("、") { audit.optJSONObject(it)?.optString("name").orEmpty() }, 12f))
        }
    }
    private fun backtestCard() {
        val parent = card("最近30交易日 · 历史验证")
        parent.addView(label("日线放量突破代理模型 · 与盘中三模型分别验证", 12f))
        val input = codeInput(); input.setText(selectedCode); parent.addView(input)
        val holding = Spinner(this)
        val horizons = listOf(1, 3, 5)
        holding.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
            horizons.map { "买入后第${it}个交易日开盘退出" })
        holding.setSelection(1); parent.addView(holding)
        val cost = Spinner(this)
        val costs = listOf(10, 20, 40)
        cost.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
            costs.map { "综合成本假设 ${it} 基点（${numText(it / 100.0)}%）" })
        cost.setSelection(1); parent.addView(cost)
        val status = label("输入代码后运行；数据不足会明确显示。", 12f); parent.addView(status)
        val results = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }; parent.addView(results)
        val run = action("运行30交易日验证") { }
        var generation = 0
        run.setOnClickListener { checked(input) { code ->
            val id = ++generation
            status.text = "正在读取完整日线并验证…"; results.removeAllViews(); run.isEnabled = false
            fetch("/api/stocks/$code/backtest?days=30&holding=${horizons[holding.selectedItemPosition]}&cost_bps=${costs[cost.selectedItemPosition]}") { data, _ ->
                if (id != generation) return@fetch
                run.isEnabled = true
                if (data == null || !data.optBoolean("ok")) { status.text = "日线数据暂不可用，未生成回测结果。"; return@fetch }
                val stats = data.optJSONObject("stats") ?: JSONObject()
                status.text = "${data.optString("window_start")} — ${data.optString("window_end")}\n"+
                    "信号 ${data.optInt("signal_count")} · 已退出 ${data.optInt("completed_count")} · 待后续 ${data.optInt("pending_count")} · 无法买入 ${data.optInt("unavailable_count")}"
                textRow(results, "完成样本胜率", numText(stats.optDouble("win_rate_pct")) + "%")
                textRow(results, "平均净收益", pctText(stats.optDouble("mean_net_pct")), stats.optDouble("mean_net_pct"))
                textRow(results, "中位净收益", pctText(stats.optDouble("median_net_pct")), stats.optDouble("median_net_pct"))
                results.addView(label("规则 ${data.optString("model")} · 数据 ${data.optString("source")}", 11f))
                val trades = data.optJSONArray("trades") ?: JSONArray()
                val states = mapOf("pending_entry" to "待买入交易日", "pending_exit" to "待退出 / 无法退出", "entry_unavailable" to "开盘无法买入")
                for (i in (0 until trades.length()).reversed().take(15)) {
                    val t = trades.getJSONObject(i)
                    val outcome = if (t.optString("status") == "completed") "净收益 ${pctText(t.optDouble("net_pct"))}" else states[t.optString("status")].orEmpty()
                    results.addView(label("${t.optString("date")} · $outcome", 12f))
                }
                val notes = data.optJSONArray("notes") ?: JSONArray()
                for (i in 0 until notes.length()) results.addView(label(notes.optString(i), 11f))
            }
        } }
        parent.addView(run)
    }
    inner class NavIcon(private val kind: Int, private val tint: Int) : View(this) {
        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            canvas.save(); canvas.scale(width / 24f, height / 24f)
            val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = tint; style = Paint.Style.STROKE; strokeWidth = 1.8f; strokeJoin = Paint.Join.ROUND; strokeCap = Paint.Cap.ROUND }
            val path = Path()
            when(kind) {
                0 -> { path.moveTo(3f, 10f); path.lineTo(12f, 3f); path.lineTo(21f, 10f); path.moveTo(5f, 9f); path.lineTo(5f, 21f); path.lineTo(10f,21f); path.lineTo(10f,15f); path.lineTo(14f,15f); path.lineTo(14f,21f); path.lineTo(19f,21f); path.lineTo(19f,9f) }
                1 -> { path.moveTo(12f,3f); path.lineTo(15f,9f); path.lineTo(22f,10f); path.lineTo(17f,15f); path.lineTo(18f,22f); path.lineTo(12f,19f); path.lineTo(6f,22f); path.lineTo(7f,15f); path.lineTo(2f,10f); path.lineTo(9f,9f); path.close() }
                2 -> { canvas.drawRoundRect(3f,4f,21f,21f,2f,2f,p); path.moveTo(6f,16f); path.lineTo(10f,11f); path.lineTo(14f,14f); path.lineTo(18f,8f) }
                else -> { canvas.drawRoundRect(4f,3f,20f,21f,2f,2f,p); for(y in listOf(8f,12f,16f)) canvas.drawLine(8f,y,16f,y,p) }
            }
            canvas.drawPath(path,p); canvas.restore()
        }
    }
    inner class MinuteChart : View(this) {
        private val p = Paint(Paint.ANTI_ALIAS_FLAG)
        private var prices = emptyList<Float>()
        private var volumes = emptyList<Float>()
        private var times = emptyList<String>()
        fun setBars(bars: JSONArray) {
            val rows = (0 until bars.length()).mapNotNull { bars.optJSONObject(it) }
            val day = rows.lastOrNull()?.optString("time")?.take(10)
            val points = rows.filter { it.optString("time").take(10) == day && it.optDouble("close").isFinite() && it.optDouble("close") > 0 }
            prices = points.map { it.optDouble("close").toFloat() }
            volumes = points.map { it.optDouble("volume", 0.0).let { v -> if (v.isFinite()) v.coerceAtLeast(0.0).toFloat() else 0f } }
            times = points.map { it.optString("time").substringAfter(" ").take(5) }
            invalidate()
        }
        override fun onDraw(c: Canvas) {
            super.onDraw(c)
            c.drawColor(Color.WHITE)
            val left = dp(45).toFloat(); val right = width - dp(8).toFloat()
            val top = dp(14).toFloat(); val bottom = height * .72f
            p.color = Color.rgb(224, 231, 239); p.strokeWidth = 1f
            for (i in 0..2) { val y = top + (bottom-top)*i/2; c.drawLine(left,y,right,y,p) }
            if (prices.isEmpty()) {
                p.color = muted; p.textSize = dp(13).toFloat()
                c.drawText("暂无分时数据", left + dp(12), (top+bottom)/2, p); return
            }
            val lo = prices.minOrNull() ?: return; val hi = prices.maxOrNull() ?: return
            val range = (hi-lo).coerceAtLeast(.01f)
            p.color = Color.GRAY; p.textSize = dp(10).toFloat()
            c.drawText(String.format("%.2f",hi),0f,top+dp(4),p)
            c.drawText(String.format("%.2f",lo),0f,bottom,p)
            val maxVol = (volumes.maxOrNull() ?: 1f).coerceAtLeast(1f)
            for (i in prices.indices) {
                val x = left + (right-left)*i/maxOf(1, prices.size-1)
                val y = bottom - (prices[i]-lo)/range*(bottom-top)
                if (prices.size == 1) { p.color = Color.rgb(39,111,207); c.drawCircle(x,y,dp(3).toFloat(),p) }
                if (i > 0) {
                    val px = left + (right-left)*(i-1)/maxOf(1, prices.size-1)
                    val py = bottom - (prices[i-1]-lo)/range*(bottom-top)
                    p.color = Color.rgb(39, 111, 207); p.strokeWidth = dp(2).toFloat()
                    c.drawLine(px,py,x,y,p)
                }
                p.color = Color.rgb(166, 192, 221)
                p.strokeWidth = maxOf(1f,(right-left)/prices.size*.7f)
                c.drawLine(x,height-dp(22).toFloat(),x,height-dp(22)-volumes[i]/maxVol*(height-bottom-dp(34)),p)
            }
            p.color = Color.GRAY; p.textSize = dp(10).toFloat()
            c.drawText(times.first(),left,height-dp(4).toFloat(),p)
            c.drawText(times.last(),right-dp(30),height-dp(4).toFloat(),p)
        }
    }
}
