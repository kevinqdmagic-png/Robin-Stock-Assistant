package com.robin.stock

import android.graphics.*
import android.os.Bundle
import android.view.View
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {
    private val base = "https://robin-stock-api-production.up.railway.app"
    private val prefs by lazy { getSharedPreferences("robin", MODE_PRIVATE) }
    private lateinit var root: LinearLayout
    private lateinit var chart: MinuteChart
    private lateinit var minuteStatus: TextView
    private lateinit var stockInput: EditText
    private lateinit var stockTitle: TextView
    private var selectedCode = ""
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
    private fun label(value: String, size: Float = 15f, bold: Boolean = false) = TextView(this).apply {
        text = value; textSize = size; setTextColor(if (bold) Color.rgb(29, 48, 78) else Color.rgb(78, 94, 113))
        setPadding(0, dp(5), 0, dp(5))
        if (bold) setTypeface(typeface, Typeface.BOLD)
    }
    private fun card(title: String) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(14), dp(16), dp(14))
        background = android.graphics.drawable.GradientDrawable().apply {
            setColor(Color.WHITE); cornerRadius = dp(14).toFloat()
        }
        elevation = dp(2).toFloat()
        root.addView(this, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(14) })
        addView(label(title, 19f, true))
    }
    private fun request(path: String): JSONObject {
        val conn = URL(base + path).openConnection() as HttpURLConnection
        conn.connectTimeout = 12000; conn.readTimeout = 25000
        try {
            if (conn.responseCode !in 200..299) error("HTTP ${conn.responseCode}")
            return JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
        } finally { conn.disconnect() }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(18), dp(18), dp(18), dp(30))
            setBackgroundColor(Color.rgb(245, 247, 251))
        }
        setContentView(ScrollView(this).apply { addView(root) })
        root.addView(label("Robin 股票助手", 26f, true))
        root.addView(label("市场观察 · 北京时间 · 数据状态以页面为准", 13f))
        val market = card("市场扫描")
        val marketStatus = label("读取中…")
        val candidates = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        market.addView(marketStatus); market.addView(candidates)
        market.addView(Button(this).apply { text = "刷新动态候选"; setOnClickListener { loadMarket(marketStatus, candidates) } })
        val minute = card("个股分时")
        val selected = label("输入六位代码查看", 15f, true)
        stockTitle = selected
        minute.addView(selected)
        val input = EditText(this).apply {
            hint = "股票代码，例如 300502"; inputType = android.text.InputType.TYPE_CLASS_NUMBER
            filters = arrayOf(android.text.InputFilter.LengthFilter(6))
        }
        stockInput = input
        minute.addView(input)
        minute.addView(Button(this).apply {
            text = "查看分时并保存自选"
            setOnClickListener {
                val code = input.text.toString()
                if (!code.matches(Regex("[0-9]{6}"))) { input.error = "请输入六位股票代码"; return@setOnClickListener }
                prefs.edit().putString("watch", code).apply(); loadMinute(code, selected)
            }
        })
        minuteStatus = label("选择自选股或候选股后加载分钟数据。", 13f)
        chart = MinuteChart()
        minute.addView(minuteStatus)
        minute.addView(chart, LinearLayout.LayoutParams(-1, dp(250)))
        val saved = prefs.getString("watch", "") ?: ""
        if (saved.matches(Regex("[0-9]{6}"))) { input.setText(saved); loadMinute(saved, selected) }
        card("买点观察").addView(label("尚无经验证的实时信号。低位首次启动、分歧转一致、超跌转强将在信号服务接入后显示。"))
        val research = card("每日研究")
        val researchStatus = label("读取研究记录中…")
        research.addView(researchStatus)
        research.addView(Button(this).apply { text = "刷新研究记录"; setOnClickListener { loadResearch(researchStatus) } })
        loadMarket(marketStatus, candidates); loadResearch(researchStatus)
    }
    private fun loadMarket(status: TextView, box: LinearLayout) {
        status.text = "正在读取全 A 行情…"
        thread {
            try {
                val data = request("/api/market")
                runOnUiThread {
                    box.removeAllViews()
                    if (!data.optBoolean("ok")) { status.text = "行情暂不可用：${data.optString("status")}"; return@runOnUiThread }
                    status.text = "${data.optString("time_cn")} 更新｜${data.optInt("count")} 只｜上涨 ${data.optInt("advance")}｜下跌 ${data.optInt("decline")}\n来源 ${data.optString("source")} · 初筛排序，不是买入信号"
                    val rows = data.optJSONArray("candidates") ?: JSONArray()
                    for (i in 0 until minOf(20, rows.length())) {
                        val x = rows.getJSONObject(i); val code = x.optString("code")
                        box.addView(label("${i+1}. ${x.optString("name")}  $code   ¥${x.optString("price")}  ${x.optString("pct")}%\n量比 ${x.optString("volume_ratio")} · 换手 ${x.optString("turnover")}%").apply {
                            setPadding(0, dp(8), 0, dp(8))
                            setOnClickListener { stockInput.setText(code); loadMinute(code, stockTitle) }
                        })
                    }
                }
            } catch (e: Exception) { runOnUiThread { status.text = "行情连接失败：${e.message}" } }
        }
    }
    private fun loadMinute(code: String, title: TextView) {
        selectedCode = code; title.text = "$code 分时"; minuteStatus.text = "正在读取分钟数据…"; chart.setBars(JSONArray())
        thread {
            try {
                val data = request("/api/stocks/$code/minute")
                runOnUiThread {
                    if (selectedCode != code) return@runOnUiThread
                    val bars = data.optJSONArray("bars") ?: JSONArray()
                    if (!data.optBoolean("ok") || bars.length() == 0) {
                        minuteStatus.text = "分时暂不可用：${data.optString("status")}。请稍后刷新。"; return@runOnUiThread
                    }
                    chart.setBars(bars)
                    minuteStatus.text = "${bars.length()} 条一分钟数据｜最后一条 ${bars.getJSONObject(bars.length()-1).optString("time")}｜请求时间 ${data.optString("time_cn")}\n收盘后显示历史数据；更新时间不代表实时推送。"
                }
            } catch (e: Exception) { runOnUiThread { if (selectedCode == code) minuteStatus.text = "分时连接失败：${e.message}" } }
        }
    }
    private fun loadResearch(status: TextView) {
        status.text = "正在读取研究记录…"
        thread {
            try {
                val data = request("/api/research")
                runOnUiThread {
                    val rows = data.optJSONArray("items") ?: JSONArray()
                    status.text = if (rows.length() == 0) "尚无已发布研究记录。盘后复盘、龙虎榜、低位启动样本、量化交易研究将逐项接入；未运行的任务不会标为完成。"
                    else (0 until minOf(rows.length(), 12)).joinToString("\n\n") { i ->
                        val x = rows.getJSONObject(i)
                        "${x.optString("date")} · ${x.optString("track")}\n${x.optString("title")}\n${x.optString("summary")}"
                    }
                }
            } catch (e: Exception) { runOnUiThread { status.text = "研究记录暂不可用：${e.message}" } }
        }
    }
    inner class MinuteChart : View(this) {
        private val p = Paint(Paint.ANTI_ALIAS_FLAG)
        private var prices = emptyList<Float>()
        private var volumes = emptyList<Float>()
        fun setBars(bars: JSONArray) {
            val points = (0 until bars.length()).mapNotNull { i ->
                bars.optJSONObject(i)?.let { x ->
                    val value = x.optDouble("close")
                    if (value.isFinite() && value > 0) Pair(value.toFloat(), x.optDouble("volume", 0.0).toFloat()) else null
                }
            }
            prices = points.map { it.first }; volumes = points.map { it.second }; invalidate()
        }
        override fun onDraw(c: Canvas) {
            super.onDraw(c)
            c.drawColor(Color.WHITE)
            val left = dp(45).toFloat(); val right = width - dp(8).toFloat()
            val top = dp(14).toFloat(); val bottom = height * .72f
            p.color = Color.rgb(224, 231, 239); p.strokeWidth = 1f
            for (i in 0..2) { val y = top + (bottom-top)*i/2; c.drawLine(left,y,right,y,p) }
            if (prices.size < 2) return
            val lo = prices.minOrNull() ?: return; val hi = prices.maxOrNull() ?: return
            val range = (hi-lo).coerceAtLeast(.01f)
            p.color = Color.GRAY; p.textSize = dp(10).toFloat()
            c.drawText(String.format("%.2f",hi),0f,top+dp(4),p)
            c.drawText(String.format("%.2f",lo),0f,bottom,p)
            val maxVol = (volumes.maxOrNull() ?: 1f).coerceAtLeast(1f)
            for (i in prices.indices) {
                val x = left + (right-left)*i/(prices.size-1)
                val y = bottom - (prices[i]-lo)/range*(bottom-top)
                if (i > 0) {
                    val px = left + (right-left)*(i-1)/(prices.size-1)
                    val py = bottom - (prices[i-1]-lo)/range*(bottom-top)
                    p.color = Color.rgb(39, 111, 207); p.strokeWidth = dp(2).toFloat()
                    c.drawLine(px,py,x,y,p)
                }
                p.color = Color.rgb(166, 192, 221)
                p.strokeWidth = maxOf(1f,(right-left)/prices.size*.7f)
                c.drawLine(x,height-dp(22).toFloat(),x,height-dp(22)-volumes[i]/maxVol*(height-bottom-dp(34)),p)
            }
            p.color = Color.GRAY; p.textSize = dp(10).toFloat()
            c.drawText("09:30",left,height-dp(4).toFloat(),p)
            c.drawText("15:00",right-dp(30),height-dp(4).toFloat(),p)
        }
    }
}
