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
    private val red = Color.rgb(232, 49, 62)
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
            val data = runCatching { request(path) }
            runOnUiThread {
                if (!isDestroyed && generation == pageGeneration) result(data.getOrNull(), data.exceptionOrNull()?.message)
            }
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        selectedCode = savedInstanceState?.getString("code") ?: prefs.getString("selected", prefs.getString("watch", "")).orEmpty()
        val shell = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Color.rgb(246, 246, 248)) }
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
        root.addView(label(when(index) { 0 -> "看市场 · 等确认 · 留记录"; 1 -> "我的关注 · 保存在本机"; 2 -> "分钟走势 · 北京时间"; else -> "每日复盘与研究档案" }, 13f).apply { setPadding(0, 0, 0, dp(18)) })
        when (index) { 0 -> home(); 1 -> watchlist(); 2 -> minuteCard(); else -> research() }
    }
    private fun home() {
        val market = card("市场概览")
        val status = label("正在读取行情…", 13f); market.addView(status)
        val candidates = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        homeMarketStatus = status
        homeCandidatesBox = candidates
        market.addView(action("刷新市场") { loadMarket(status, candidates) })
        val signalCard = card("买点观察")
        val signalStatus = label("正在扫描观察信号…", 16f, true)
        val signalBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        signalCard.addView(signalStatus)
        signalCard.addView(label("低位首次启动 · 分歧转一致 · 超跌转强", 13f))
        signalCard.addView(signalBox)
        signalCard.addView(action("刷新买点观察") { loadSignals(signalStatus, signalBox) })
        minuteCard()
        val pool = card("动态候选")
        pool.addView(label("量价初筛，仅供观察", 13f)); pool.addView(candidates)
        loadMarket(status, candidates)
        loadSignals(signalStatus, signalBox)
        startHomeAutoRefresh()
    }

    private fun startHomeAutoRefresh() {
        stopHomeAutoRefresh()
        if (!isForeground || currentTab != 0) return
        val task = object : Runnable {
            override fun run() {
                if (!isForeground || currentTab != 0) return
                val status = homeMarketStatus ?: return
                val box = homeCandidatesBox ?: return
                loadLiveCandidates(box)
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
        if (!updatedAt.isNullOrBlank()) {
            box.addView(label("自动更新 · $updatedAt", 11f))
        }
        for (i in 0 until minOf(20, rows.length())) {
            val x = rows.getJSONObject(i); val code = x.optString("code").takeLast(6)
            box.addView(label("${x.optString("name")}  $code   ¥${x.optString("price")}\n${x.optString("pct")}%  ·  量比 ${x.optString("volume_ratio")}  ·  换手 ${x.optString("turnover")}%").apply {
                setTextColor(ink); setPadding(0, dp(12), 0, dp(12))
                setOnClickListener { selectedCode = code; showTab(2) }
            })
        }
    }

    private fun loadLiveCandidates(box: LinearLayout) {
        fetch("/api/candidates?limit=20") { data, _ ->
            if (data == null || !data.optBoolean("ok")) return@fetch
            val rows = data.optJSONArray("candidates") ?: return@fetch
            renderCandidates(box, rows, data.optString("time_cn"))
        }
    }

    private fun loadMarket(status: TextView, box: LinearLayout) {
        status.text = "正在读取全 A 行情…"; box.removeAllViews()
        fetch("/api/market") { data, error ->
            if (data == null || !data.optBoolean("ok")) {
                status.text = "行情暂不可用，请稍后刷新。" + (error?.let { "\n$it" } ?: ""); return@fetch
            }
            status.text = "上涨 ${data.optInt("advance")}  ·  下跌 ${data.optInt("decline")}\n扫描 ${data.optInt("count")} 只 · ${data.optString("time_cn")}\n来源 ${data.optString("source")} · 北京时间\n动态候选每30秒自动刷新"
            renderCandidates(box, data.optJSONArray("candidates") ?: JSONArray(), data.optString("time_cn"))
        }
    }
    private fun research() {
        val names = mapOf("market_review" to "每日复盘", "dragon_tiger" to "龙虎榜研究", "low_position" to "低位启动跟踪", "quant_research" to "量化交易研究")
        card("研究栏目").addView(label(names.values.joinToString(" · "), 14f))
        val records = card("研究记录")
        val status = label("正在读取已发布记录…", 13f); records.addView(status)
        val items = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }; records.addView(items)
        fun load() {
            status.text = "正在读取已发布记录…"; items.removeAllViews()
            fetch("/api/research") { data, error ->
                if (data == null || !data.optBoolean("ok")) {
                    status.text = "研究记录暂不可用，请稍后刷新。" + (error?.let { "\n$it" } ?: ""); return@fetch
                }
                val rows = data.optJSONArray("items") ?: JSONArray()
                status.text = if (rows.length() == 0) "尚无已发布研究。每日任务的结果需要同步发布后才能在这里查看。" else "已发布 ${rows.length()} 篇 · 北京时间"
                for (i in 0 until rows.length()) {
                    val x = rows.getJSONObject(i)
                    items.addView(label("${x.optString("date")} · ${names[x.optString("track")] ?: x.optString("track")}", 12f))
                    items.addView(label(x.optString("title"), 17f, true))
                    items.addView(label(x.optString("summary"), 15f).apply { setTextColor(ink); setTextIsSelectable(true); setPadding(0, dp(4), 0, dp(22)) })
                }
            }
        }
        records.addView(action("刷新研究") { load() }); load()
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
