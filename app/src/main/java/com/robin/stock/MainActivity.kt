package com.robin.stock

import android.app.DownloadManager
import android.content.Intent
import android.graphics.*
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private val base = "https://robin-stock-api-production.up.railway.app"
    private val prefs by lazy { getSharedPreferences("robin", MODE_PRIVATE) }
    private val appVersionName by lazy { packageManager.getPackageInfo(packageName, 0).versionName ?: "0.0.0" }
    private val executor = Executors.newFixedThreadPool(3)
    private val homeRefreshHandler = Handler(Looper.getMainLooper())
    private val updateHandler = Handler(Looper.getMainLooper())
    private var updatePollTask: Runnable? = null
    private var updateStatusView: TextView? = null
    private val autoRefreshMs = 30_000L
    private val red = Color.rgb(218, 45, 61)
    private val green = Color.rgb(20, 143, 102)
    private var overviewBox: LinearLayout? = null
    private var sectorBox: LinearLayout? = null
    private var overviewData: JSONObject? = null
    private var sectorKind = "industry"
    private var homeSessionCode = ""
    private var homeSessionDate = ""
    private var homeIsLive = false
    private var refreshTick = 0
    private val ink = Color.rgb(35, 38, 44)
    private val muted = Color.rgb(122, 126, 134)
    private lateinit var root: LinearLayout
    private lateinit var scroller: ScrollView
    private lateinit var nav: LinearLayout
    private var researchTask = ""
    private var researchTaskTitle = ""
    private var researchCode = ""
    private var researchStockName = ""
    private var stockCatalog = JSONObject()
    private var catalogOffline = true
    private var taskRefreshAction: (() -> Unit)? = null
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
        return WatchlistPolicy.codes((saved ?: prefs.getString("watch", "").orEmpty()).split(","))
    }
    private fun saveWatch(code: String) {
        prefs.edit().putString("watchlist", (watchCodes() + code).distinct().joinToString(",")).apply()
        Toast.makeText(this, "已加入自选", Toast.LENGTH_SHORT).show()
    }
    private fun researchStock(code: String): JSONObject? {
        val rows = stockCatalog.optJSONArray("items") ?: return null
        return (0 until rows.length()).mapNotNull { rows.optJSONObject(it) }.firstOrNull { it.optString("code") == code }
    }
    private fun stockHistory(stock: JSONObject): List<JSONObject> {
        val rows = stock.optJSONArray("history") ?: JSONArray()
        return (0 until rows.length()).mapNotNull { rows.optJSONObject(it) }.sortedBy { it.optString("date") }
    }
    private fun roleName(stock: JSONObject) = when (stock.optString("role")) {
        "core" -> "原研究核心观察"; "comparison" -> "补充比较"; else -> "产业链研究观察"
    }
    private fun applyCatalog(data: JSONObject): Boolean {
        val rows = data.optJSONArray("items") ?: return false
        if (data.optInt("schema_version") != 1 || (0 until rows.length()).any {
            val stock = rows.optJSONObject(it)
            stock == null || !validCode.matches(stock.optString("code")) || stock.optString("name").isBlank() ||
                (stock.optJSONArray("history")?.length() ?: 0) == 0
        }) return false
        stockCatalog = data
        val defaults = (0 until rows.length()).mapNotNull { rows.optJSONObject(it) }
            .filter { it.optBoolean("default_watch") }.map { it.optString("code") }
        val result = WatchlistPolicy.seed(watchCodes(), prefs.getString("research_seeded_codes", "").orEmpty().split(","), defaults)
        prefs.edit().putString("watchlist", result.watchlist.joinToString(","))
            .putString("research_seeded_codes", result.seededCodes.joinToString(",")).apply()
        return true
    }
    private fun loadBundledCatalog() {
        val cached = runCatching { JSONObject(prefs.getString("research_stock_catalog", "").orEmpty()) }.getOrNull()
        if (cached != null && applyCatalog(cached)) return
        runCatching { assets.open("research_stocks.json").bufferedReader().use { JSONObject(it.readText()) } }
            .getOrNull()?.let { applyCatalog(it) }
    }
    private fun refreshCatalog(done: (Boolean) -> Unit) {
        fetch("/api/research-stocks") { data, _ ->
            val fresh = data != null && data.optBoolean("ok") && applyCatalog(data)
            catalogOffline = !fresh || data?.optBoolean("_offline") == true
            if (fresh) prefs.edit().putString("research_stock_catalog", data.toString()).apply()
            done(fresh)
        }
    }
    private fun openStock(code: String) { selectedCode = code; showTab(2) }
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
                    if (it.optBoolean("ok") && (path.startsWith("/api/research") || path.startsWith("/api/recommendations?") || path.startsWith("/api/tasks") || path.startsWith("/api/task-runs") || path.endsWith("/research")))
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
        loadBundledCatalog()
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
        taskRefreshAction?.invoke()
        resumePendingUpdateIfReady()
        startHomeAutoRefresh()
    }
    override fun onPause() {
        isForeground = false
        stopHomeAutoRefresh()
        super.onPause()
    }
    override fun onDestroy() {
        stopHomeAutoRefresh()
        updatePollTask?.let { updateHandler.removeCallbacks(it) }
        executor.shutdownNow()
        super.onDestroy()
    }
    @Deprecated("Legacy back handling")
    override fun onBackPressed() { if (currentTab != 0) showTab(0) else super.onBackPressed() }
    private fun showTab(index: Int) {
        stopHomeAutoRefresh()
        taskRefreshAction = null
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

    private fun requestAbsolute(url: String): JSONObject {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 12000; conn.readTimeout = 25000
        conn.setRequestProperty("Accept", "application/vnd.github+json")
        conn.setRequestProperty("User-Agent", "Robin-Stock-Assistant/" + appVersionName)
        try {
            if (conn.responseCode !in 200..299) error("HTTP ${conn.responseCode}")
            return JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
        } finally { conn.disconnect() }
    }
    private fun versionParts(value: String): List<Int> {
        val clean = value.trim().removePrefix("v").substringBefore("-")
        val parts = clean.split(".").map { token -> token.filter { it.isDigit() }.toIntOrNull() ?: 0 }
        return List(3) { index -> parts.getOrElse(index) { 0 } }
    }
    private fun isNewerVersion(latest: String, current: String): Boolean {
        val a = versionParts(latest); val b = versionParts(current)
        for (i in 0..2) {
            if (a[i] != b[i]) return a[i] > b[i]
        }
        return false
    }
    private fun checkForUpdate(status: TextView) {
        status.text = "正在检查正式版本…"
        executor.execute {
            val result = runCatching {
                requestAbsolute("https://api.github.com/repos/kevinqdmagic-png/Robin-Stock-Assistant/releases/latest")
            }
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                val release = result.getOrNull()
                if (release == null) {
                    val missingRelease = result.exceptionOrNull()?.message?.contains("404") == true
                    status.text = if (missingRelease) "目前还没有可升级的固定签名正式版。" else "检查更新失败，请稍后再试。"
                    return@runOnUiThread
                }
                val latest = release.optString("tag_name").removePrefix("v").ifBlank { release.optString("name") }
                if (latest.isBlank()) {
                    status.text = "版本信息异常，未执行更新。"; return@runOnUiThread
                }
                if (!isNewerVersion(latest, appVersionName)) {
                    status.text = "当前 ${appVersionName} 已是最新版。"
                    return@runOnUiThread
                }
                val assets = release.optJSONArray("assets") ?: JSONArray()
                val apk = (0 until assets.length()).mapNotNull { assets.optJSONObject(it) }
                    .firstOrNull { it.optString("name").endsWith(".apk", ignoreCase = true) }
                val url = apk?.optString("browser_download_url").orEmpty()
                if (url.isBlank()) {
                    status.text = "发现 $latest，但正式 APK 尚未发布。"; return@runOnUiThread
                }
                val digest = apk?.optString("digest").orEmpty()
                    .removePrefix("sha256:").trim().lowercase()
                val notes = release.optString("body").trim().take(1200)
                AlertDialog.Builder(this)
                    .setTitle("发现新版本 $latest")
                    .setMessage("当前版本：${appVersionName}\n\n" +
                        (if (notes.isBlank()) "本次更新已发布。" else notes))
                    .setNegativeButton("稍后", null)
                    .setPositiveButton("下载更新") { _, _ ->
                        startUpdateDownload(url, latest, digest, status)
                    }
                    .show()
                status.text = "发现新版本 $latest，可手动下载升级。"
            }
        }
    }
    private fun startUpdateDownload(url: String, version: String, expectedSha256: String, status: TextView?) {
        val manager = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
        val fileName = "Robin-Stock-Assistant-$version.apk"
        val request = DownloadManager.Request(Uri.parse(url))
            .setTitle("Robin 股票助手 $version")
            .setDescription("正在下载更新")
            .setMimeType("application/vnd.android.package-archive")
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setAllowedOverMetered(true)
            .setAllowedOverRoaming(false)
            .setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, fileName)
        val id = manager.enqueue(request)
        prefs.edit()
            .putLong("pending_update_download_id", id)
            .putString("pending_update_sha256", expectedSha256)
            .putString("pending_update_version", version)
            .putBoolean("pending_update_permission_prompted", false)
            .apply()
        status?.text = "正在下载 $version… 下载完成后会调出系统更新界面。"
        pollUpdateDownload(id, status)
    }
    private fun pollUpdateDownload(id: Long, status: TextView?) {
        updatePollTask?.let { updateHandler.removeCallbacks(it) }
        val task = object : Runnable {
            override fun run() {
                val manager = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
                val cursor = manager.query(DownloadManager.Query().setFilterById(id))
                val state = cursor.use {
                    if (!it.moveToFirst()) null
                    else Pair(
                        it.getInt(it.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS)),
                        it.getInt(it.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON))
                    )
                }
                when (state?.first) {
                    DownloadManager.STATUS_SUCCESSFUL -> {
                        updatePollTask = null
                        verifyAndInstallUpdate(id, status)
                    }
                    DownloadManager.STATUS_FAILED -> {
                        updatePollTask = null
                        status?.text = "更新下载失败（${state.second}），请稍后重新检查。"
                        clearPendingUpdate()
                    }
                    else -> updateHandler.postDelayed(this, 1200)
                }
            }
        }
        updatePollTask = task
        updateHandler.post(task)
    }
    private fun sha256(uri: Uri): String {
        val digest = MessageDigest.getInstance("SHA-256")
        contentResolver.openInputStream(uri)?.use { input ->
            val buffer = ByteArray(8192)
            while (true) {
                val count = input.read(buffer)
                if (count <= 0) break
                digest.update(buffer, 0, count)
            }
        } ?: error("无法读取已下载 APK")
        return digest.digest().joinToString("") { byte -> "%02x".format(byte) }
    }
    private fun verifyAndInstallUpdate(id: Long, status: TextView?) {
        val manager = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
        val uri = manager.getUriForDownloadedFile(id)
        if (uri == null) {
            status?.text = "下载文件不可用，请重新检查更新。"; clearPendingUpdate(); return
        }
        val expected = prefs.getString("pending_update_sha256", "").orEmpty().lowercase()
        status?.text = if (expected.isBlank()) "下载完成，正在准备系统更新…" else "下载完成，正在校验安装包…"
        executor.execute {
            val verified = runCatching {
                expected.isBlank() || sha256(uri).equals(expected, ignoreCase = true)
            }.getOrDefault(false)
            runOnUiThread {
                if (!verified) {
                    status?.text = "安装包校验失败，已停止更新。"
                    clearPendingUpdate()
                    return@runOnUiThread
                }
                openPackageInstaller(id, status)
            }
        }
    }
    private fun openPackageInstaller(id: Long, status: TextView?) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !packageManager.canRequestPackageInstalls()) {
            val alreadyPrompted = prefs.getBoolean("pending_update_permission_prompted", false)
            status?.text = "请在系统设置中允许“Robin股票助手”安装未知应用，然后返回继续。"
            if (!alreadyPrompted) {
                prefs.edit().putBoolean("pending_update_permission_prompted", true).apply()
                startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
            }
            return
        }
        val manager = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
        val uri = manager.getUriForDownloadedFile(id)
        if (uri == null) {
            status?.text = "安装包不可用，请重新下载。"; clearPendingUpdate(); return
        }
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        status?.text = "请在 Android 系统界面点击“更新”。"
        startActivity(intent)
        clearPendingUpdate()
    }
    private fun resumePendingUpdateIfReady() {
        val id = prefs.getLong("pending_update_download_id", -1L)
        if (id <= 0) return
        val manager = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
        val cursor = manager.query(DownloadManager.Query().setFilterById(id))
        val state = cursor.use {
            if (!it.moveToFirst()) null else it.getInt(it.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
        }
        if (state == DownloadManager.STATUS_SUCCESSFUL) verifyAndInstallUpdate(id, updateStatusView)
        else if (state == DownloadManager.STATUS_FAILED) clearPendingUpdate()
    }
    private fun clearPendingUpdate() {
        prefs.edit()
            .remove("pending_update_download_id")
            .remove("pending_update_sha256")
            .remove("pending_update_version")
            .remove("pending_update_permission_prompted")
            .apply()
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
        val settings = card("设置 / 关于")
        settings.addView(label("Robin 股票助手  ${appVersionName}", 15f, true))
        val updateStatus = label("不会自动检查更新；需要时手动检查。", 12f)
        updateStatusView = updateStatus
        settings.addView(updateStatus)
        settings.addView(action("检查更新") { checkForUpdate(updateStatus) })
        settings.addView(label("更新包由 Android 系统验证签名。首次从旧测试签名迁移到固定正式签名时，可能需要一次重新安装。", 11f))
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
            overviewData = data
            val session = data.optJSONObject("session")
            homeIsLive = session?.optBoolean("is_live") == true
            homeSessionCode = session?.optString("code").orEmpty()
            homeSessionDate = session?.optString("date").orEmpty().ifBlank {
                java.time.ZonedDateTime.now(java.time.ZoneId.of("Asia/Shanghai")).toLocalDate().toString()
            }
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
                val clock = java.time.ZonedDateTime.now(java.time.ZoneId.of("Asia/Shanghai"))
                val decision = MarketRefreshPolicy.decide(
                    dayOfWeek = clock.dayOfWeek.value,
                    hour = clock.hour,
                    minute = clock.minute,
                    currentDate = clock.toLocalDate().toString(),
                    sessionDate = homeSessionDate,
                    sessionCode = homeSessionCode,
                    serverSaysLive = homeIsLive,
                    refreshTick = refreshTick,
                )
                if (decision.refreshOverview) overviewBox?.let { loadOverview(it) }
                if (decision.refreshCandidates) {
                    if (!homeIsLive) status.text = "交易时段切换中，正在恢复实时行情…"
                    loadLiveCandidates(box)
                    refreshTick = (refreshTick + 1) % 3
                }
                if (decision.refreshMarket) loadMarket(status, box)
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
        val intro = card("研究自选")
        intro.addView(label("自选直接显示价格、涨跌幅、量比和换手；点股票仍可查看研究理由与分时。", 13f))
        val status = label("正在核对最新研究…", 12f); intro.addView(status)
        val quoteStatus = label("行情：正在读取…", 12f); intro.addView(quoteStatus)
        val stockBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        card("添加自选").apply {
            val input = codeInput(); addView(input)
            addView(action("加入自选") { checked(input) { saveWatch(it); showTab(1) } })
        }
        root.addView(stockBox)

        val savedQuoteArray = runCatching {
            JSONArray(prefs.getString("watchlist_quote_cache", "[]") ?: "[]")
        }.getOrDefault(JSONArray())
        var quoteMap: Map<String, JSONObject> =
            (0 until savedQuoteArray.length()).mapNotNull { savedQuoteArray.optJSONObject(it) }
                .associateBy { it.optString("code").takeLast(6) }
        if (quoteMap.isNotEmpty()) quoteStatus.text = "行情：已显示上次数据，正在后台刷新…"

        fun persistQuotes() {
            val rows = JSONArray()
            quoteMap.values.forEach { rows.put(it) }
            prefs.edit()
                .putString("watchlist_quote_cache", rows.toString())
                .putLong("watchlist_quote_cache_saved_at", System.currentTimeMillis())
                .apply()
        }

        fun render() {
            stockBox.removeAllViews()
            val codes = watchCodes()
            status.text = (if (catalogOffline) "本机研究档案 · " else "已同步研究 · ") + "${codes.size} 只自选"
            if (codes.isEmpty()) stockBox.addView(label("还没有自选股。输入代码添加，或从下方研究清单选择。"))
            codes.forEach { code ->
                val stock = researchStock(code)
                val quote = quoteMap[code]
                val displayName = quote?.optString("name")?.takeIf { it.isNotBlank() }
                    ?: stock?.optString("name")?.takeIf { it.isNotBlank() }
                    ?: "股票"
                val item = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(12), dp(16), dp(14))
                    background = surface(Color.WHITE)
                    setOnClickListener { openStock(code) }
                }

                val header = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
                header.addView(label("$displayName  $code", 20f, true), LinearLayout.LayoutParams(0, -2, 1f))
                if (quote != null) {
                    val pct = quote.optDouble("pct", Double.NaN)
                    header.addView(label(pctText(pct), 18f, true).apply {
                        setTextColor(trendColor(pct)); gravity = Gravity.END
                    })
                }
                item.addView(header)

                if (quote != null) {
                    val price = quote.optDouble("price", Double.NaN)
                    val volumeRatio = quote.optDouble("volume_ratio", Double.NaN)
                    val turnover = quote.optDouble("turnover", Double.NaN)
                    item.addView(label(
                        "¥${numText(price)}  ·  量比 ${numText(volumeRatio)}  ·  换手 ${numText(turnover)}%",
                        13f
                    ).apply { setTextColor(ink) })
                } else {
                    item.addView(label("行情读取中…", 12f))
                }

                if (stock != null) {
                    item.addView(label("${roleName(stock)} · ${stock.optString("sector")}", 12f))
                    item.addView(label(stockHistory(stock).firstOrNull()?.optString("reason").orEmpty(), 14f).apply { setTextColor(ink) })
                } else item.addView(label("手动自选 · 暂无已归档的推荐理由", 12f))

                val row = LinearLayout(this)
                row.addView(action("推荐理由 / 分时") { openStock(code) }, LinearLayout.LayoutParams(0, -2, 1f))
                row.addView(action("移除") {
                    prefs.edit().putString("watchlist", watchCodes().filter { it != code }.joinToString(",")).apply()
                    quoteMap = quoteMap - code
                    render()
                }, LinearLayout.LayoutParams(0, -2, 1f))
                item.addView(row)
                stockBox.addView(item, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(12) })
            }
        }

        fun refreshQuotes(followUp: Boolean = false) {
            val codes = watchCodes()
            if (codes.isEmpty()) {
                quoteStatus.text = "行情：暂无自选"
                quoteMap = emptyMap()
                persistQuotes()
                render()
                return
            }
            quoteStatus.text = if (quoteMap.isEmpty()) "行情：正在读取…" else "行情：已显示最近数据，正在刷新…"
            fetch("/api/quotes?codes=${codes.joinToString(",")}") { data, _ ->
                if (data == null || !data.optBoolean("ok")) {
                    quoteStatus.text = if (quoteMap.isEmpty())
                        "行情暂不可用，稍后点“刷新行情”重试。"
                    else "行情：暂用最近一次数据，后台行情稍后再试。"
                    render()
                    return@fetch
                }
                val rows = data.optJSONArray("items") ?: JSONArray()
                val merged = quoteMap.toMutableMap()
                for (i in 0 until rows.length()) {
                    val row = rows.optJSONObject(i) ?: continue
                    val code = row.optString("code").takeLast(6)
                    if (code.length == 6) merged[code] = row
                }
                quoteMap = merged
                persistQuotes()
                val refreshing = data.optBoolean("refreshing")
                val age = data.optInt("cache_age_sec", 0)
                quoteStatus.text = when {
                    refreshing && age > 0 -> "行情：秒开缓存 · ${age}秒前，后台更新中…"
                    data.optString("status") == "partial" -> "行情：部分股票暂缺 · ${data.optString("time_cn")} 北京时间"
                    else -> "行情：${data.optString("time_cn")} · 北京时间"
                }
                render()
                if (refreshing && !followUp) {
                    updateHandler.postDelayed({ refreshQuotes(true) }, 2500L)
                }
            }
        }

        val refreshRow = LinearLayout(this)
        refreshRow.addView(action("刷新行情") { refreshQuotes() }, LinearLayout.LayoutParams(0, -2, 1f))
        refreshRow.addView(action("刷新研究理由") { refreshCatalog { render() } }, LinearLayout.LayoutParams(0, -2, 1f))
        intro.addView(refreshRow)

        render()
        refreshQuotes()
        refreshCatalog { render() }

        val restore = card("过去研究清单")
        val choices = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = View.GONE }
        val toggle = action("展开清单，选择重新加入") { }
        toggle.setOnClickListener {
            choices.visibility = if (choices.visibility == View.VISIBLE) View.GONE else View.VISIBLE
            choices.removeAllViews()
            val rows = stockCatalog.optJSONArray("items") ?: JSONArray()
            for (i in 0 until rows.length()) {
                val stock = rows.getJSONObject(i); val code = stock.optString("code")
                choices.addView(action("${stock.optString("name")} $code · ${roleName(stock)}") {
                    saveWatch(code); render(); refreshQuotes()
                })
            }
        }
        restore.addView(toggle); restore.addView(choices)
    }
    private fun renderStockReason(parent: LinearLayout, code: String) {
        parent.removeAllViews()
        val stock = researchStock(code)
        if (stock == null) {
            parent.addView(label(if (validCode.matches(code)) "这只股票暂无已归档的推荐理由。" else "选择股票后可查看推荐理由。", 13f)); return
        }
        val history = stockHistory(stock)
        val first = history.firstOrNull() ?: return
        val latest = history.last()
        parent.addView(label("${stock.optString("name")} · ${roleName(stock)}", 18f, true))
        parent.addView(label("${stock.optString("sector")} · 首次研究 ${first.optString("date")} · 最近记录 ${latest.optString("date")}", 12f))
        parent.addView(label("最初为何关注", 15f, true))
        parent.addView(label(first.optString("reason"), 15f).apply { setTextColor(ink); setTextIsSelectable(true) })
        parent.addView(label("${if (catalogOffline) "本机档案 · " else ""}${latest.optString("evidence_status")}", 12f))
        if (latest.optString("fact_note").isNotBlank()) parent.addView(label("最近核验：${latest.optString("fact_note")}", 14f).apply { setTextColor(ink) })
        parent.addView(label("继续验证", 15f, true))
        val checks = latest.optJSONArray("validation") ?: JSONArray()
        for (i in 0 until checks.length()) parent.addView(label("• ${checks.optString(i)}", 14f))
        parent.addView(label("下调关注的条件：${latest.optString("risk")}", 14f))
        parent.addView(label(stockCatalog.optString("notice"), 12f))
        val records = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = View.GONE }
        val toggle = action("展开 ${history.size} 条研究记录与来源") { }
        toggle.setOnClickListener {
            records.visibility = if (records.visibility == View.VISIBLE) View.GONE else View.VISIBLE
            toggle.text = if (records.visibility == View.VISIBLE) "收起研究记录" else "展开 ${history.size} 条研究记录与来源"
        }
        history.asReversed().forEach { entry ->
            records.addView(label("${entry.optString("date")} · ${entry.optString("title")}", 15f, true))
            records.addView(label(entry.optString("reason"), 14f).apply { setTextColor(ink) })
            records.addView(label(entry.optString("evidence_status") + "\n" + entry.optString("fact_note"), 12f))
            val validation = entry.optJSONArray("validation") ?: JSONArray()
            for (i in 0 until validation.length()) records.addView(label("• ${validation.optString(i)}", 13f))
            records.addView(label("下调关注：${entry.optString("risk")}", 13f))
            val sources = entry.optJSONArray("sources") ?: JSONArray()
            for (i in 0 until sources.length()) records.addView(label(sources.optString(i), 11f).apply {
                setTextIsSelectable(true); autoLinkMask = android.text.util.Linkify.WEB_URLS
            })
        }
        parent.addView(toggle); parent.addView(records)
        parent.addView(action("查看关联研究全文") {
            researchCode = code; researchStockName = stock.optString("name"); researchTask = ""; researchTaskTitle = ""; showTab(3)
        })
    }
    private fun minuteCard() {
        val minute = card("个股研究与分时")
        val title = label("选择股票查看走势", 17f, true); minute.addView(title)
        val input = codeInput(); input.setText(selectedCode); minute.addView(input)
        val status = label("输入代码，或从自选和动态候选进入。", 12f)
        val chart = MinuteChart()
        val reason = card("推荐理由与研究记录")
        val reasonBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }; reason.addView(reasonBox)
        val chartCard = card("分钟走势")
        val row = LinearLayout(this)
        fun load(code: String) {
            selectedCode = code; prefs.edit().putString("selected", code).apply()
            title.text = "$code · 分时"; status.text = "正在读取分钟数据…"; chart.setBars(JSONArray())
            val requestId = ++minuteGeneration
            renderStockReason(reasonBox, code)
            refreshCatalog { if (requestId == minuteGeneration) renderStockReason(reasonBox, code) }
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
        minute.addView(row); chartCard.addView(status); chartCard.addView(chart, LinearLayout.LayoutParams(-1, dp(320)))
        if (validCode.matches(selectedCode)) load(selectedCode) else renderStockReason(reasonBox, "")
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
            val advance = data.optInt("advance")
            val decline = data.optInt("decline")
            val flat = data.optInt("flat")
            val mood = MarketRefreshPolicy.breadthMood(advance, decline, flat)
            status.text = "${if (complete) "全覆盖" else "覆盖口径"}情绪 ${mood.label}" +
                (mood.advancePct?.let { " · 上涨占比 ${numText(it, 1)}%" } ?: "") + "\n" +
                "上涨 $advance  ·  下跌 $decline  ·  平盘 $flat\n" +
                "${if (complete) "覆盖" else "部分覆盖"} ${data.optInt("count")} 只  ·  " +
                "${data.optString("amount_scope", "覆盖成交额")} ${numText(data.optDouble("amount_yi"))} 亿\n" +
                "读取时间 ${data.optString("time_cn")} · 北京时间" +
                if (data.optBoolean("stale")) "\n缓存已过期，请核对行情时间。" else ""
            renderCandidates(box, data.optJSONArray("candidates") ?: JSONArray(), data.optString("time_cn"))
        }
    }
    private fun research() {
        val names = linkedMapOf("" to "全部", "market_review" to "每日复盘", "volume_price" to "量价研究",
            "dragon_tiger" to "龙虎榜", "low_position" to "低位启动", "quant_research" to "量化研究", "high_elasticity" to "高弹性", "app_development" to "APK打磨")
        taskCenterCard()
        if (researchCode.isNotBlank()) {
            card("${researchStockName} $researchCode · 关联研究").apply {
                addView(label("以下全文包含这只股票的研究来源。", 12f))
                addView(action("查看全部股票研究") { researchCode = ""; researchStockName = ""; showTab(3) })
            }
        }
        if (researchTask.isNotBlank()) {
            val selection = card("当前任务：$researchTaskTitle")
            selection.addView(action("查看全部研究") { researchTask = ""; researchTaskTitle = ""; showTab(3) })
        }
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
            val path = "/api/research?limit=20&offset=$offset&track=$track&date=$filterDate&task=$researchTask&code=$researchCode"
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
                    items.addView(wrapper)
                }
                offset += rows.length()
                more.visibility = if (data.optBoolean("has_more")) View.VISIBLE else View.GONE
            }
        }
        names.forEach { (key, title) ->
            chips.addView(action(title) { researchTask = ""; researchTaskTitle = ""; track = key; load() })
        }
        archive.addView(action("按日期筛选 / 刷新") { load() })
        more.setOnClickListener { load(true) }; archive.addView(more); load()
    }
    private fun taskCenterCard() {
        val parent = card("定时任务中心")
        parent.addView(label("查看安排、执行记录和研究成果。", 12f))
        val status = label("正在读取任务…", 12f); parent.addView(status)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = View.GONE }
        val toggle = action("展开任务安排") { }
        toggle.setOnClickListener {
            box.visibility = if (box.visibility == View.VISIBLE) View.GONE else View.VISIBLE
            toggle.text = if (box.visibility == View.VISIBLE) "收起任务安排" else "展开任务安排"
        }
        parent.addView(toggle); parent.addView(box)
        val states = mapOf("running" to "执行中", "waiting" to "等待研究齐备",
            "completed" to "已完成", "blocked" to "遇到阻碍", "failed" to "执行失败",
            "report_missing" to "报告待发布")
        fun renderEvent(event: JSONObject): String {
            val source = if (event.optString("trigger") == "manual") "本次人工工作" else "定时执行"
            return "$source · ${states[event.optString("status")] ?: "状态待核验"}\n" +
                event.optString("recorded_at") + "\n" + event.optString("summary")
        }
        fun load() {
            fetch("/api/tasks") { data, _ ->
                if (data == null || !data.optBoolean("ok")) {
                    status.text = "任务记录暂不可用，请刷新重试。"; return@fetch
                }
                val rows = data.optJSONArray("items") ?: JSONArray()
                status.text = (if (data.optBoolean("_offline")) "离线缓存 · " else "") +
                    "${rows.length()}项任务 · 最近记录以实际执行回执为准\n安排更新：${data.optString("configuration_updated_at")}"
                box.removeAllViews()
                for (i in 0 until rows.length()) {
                    val task = rows.getJSONObject(i)
                    val taskId = task.optString("id")
                    val title = task.optString("title")
                    val wrapper = LinearLayout(this).apply {
                        orientation = LinearLayout.VERTICAL; setPadding(0, dp(10), 0, dp(16))
                    }
                    wrapper.addView(label(title + if (task.optBoolean("one_time")) " · 一次性" else "", 16f, true))
                    wrapper.addView(label(task.optString("schedule_text"), 12f))
                    wrapper.addView(label(task.optString("summary"), 13f))
                    val latest = task.optJSONObject("last_run")
                    wrapper.addView(label(if (latest == null) "未收到执行记录" else renderEvent(latest), 12f))
                    wrapper.addView(label("已归档 ${task.optInt("report_count")} 篇报告", 12f))
                    wrapper.addView(action("查看对应报告") {
                        researchCode = ""; researchStockName = ""
                        researchTask = taskId; researchTaskTitle = title; showTab(3)
                    })
                    val history = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = View.GONE }
                    val records = action("查看执行记录") { }
                    records.setOnClickListener {
                        if (history.visibility == View.VISIBLE) { history.visibility = View.GONE; return@setOnClickListener }
                        records.isEnabled = false
                        fetch("/api/task-runs?task=$taskId&limit=20") { result, _ ->
                            records.isEnabled = true; history.removeAllViews(); history.visibility = View.VISIBLE
                            if (result == null || !result.optBoolean("ok")) {
                                history.addView(label("执行回执暂不可用。", 12f)); return@fetch
                            }
                            if (result.optBoolean("_offline")) history.addView(label("离线缓存", 11f))
                            val events = result.optJSONArray("items") ?: JSONArray()
                            if (events.length() == 0) history.addView(label("暂无可核验执行记录；历史报告可单独查看。", 12f))
                            for (j in 0 until events.length()) history.addView(label(renderEvent(events.getJSONObject(j)), 12f))
                            if (result.optBoolean("has_more")) history.addView(label("此处显示最近20条，完整研究保存在历史报告中。", 11f))
                        }
                    }
                    wrapper.addView(records); wrapper.addView(history); box.addView(wrapper)
                }
            }
        }
        taskRefreshAction = { load() }
        parent.addView(action("刷新任务状态") { load() })
        load()
    }
    private fun recommendationCard() {
        val parent = card("每日双标 · 表现记录")
        parent.addView(label("原始推荐保留，后续结果追加；按交易日跟踪。", 12f))
        val status = label("正在读取推荐记录…", 12f); parent.addView(status)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }; parent.addView(box)
        var offset = 0
        var requestId = 0
        var loading = false
        val more = action("加载更早推荐") { }.apply { visibility = View.GONE }
        fun load(append: Boolean = false) {
        if (loading) return
        if (!append) {
            offset = 0
            box.removeAllViews()
            more.visibility = View.GONE
        }
        val requestedOffset = offset
        val id = ++requestId
        loading = true; more.isEnabled = false
        fetch("/api/recommendations?limit=12&offset=$requestedOffset") { data, _ ->
            if (id != requestId) return@fetch
            loading = false
            more.isEnabled = true
            if (data == null || !data.optBoolean("ok")) {
                status.text = "推荐记录暂不可用，请稍后刷新。"; return@fetch
            }
            val rows = data.optJSONArray("items") ?: JSONArray()
            val total = data.optInt("total", rows.length())
            val loaded = requestedOffset + rows.length()
            status.text = (if (data.optBoolean("_offline")) "离线缓存 · " else "") +
                "已显示 $loaded / $total 条"
            if (rows.length() == 0 && requestedOffset == 0) box.addView(label("历史推荐正在补证。缺少当时价格或时间的记录不计算收益。", 13f))
            val groups = mapOf("close" to "盘后组", "0950" to "早盘9:50", "1440" to "尾盘14:40")
            for (i in 0 until rows.length()) {
                val row = rows.getJSONObject(i)
                val code = row.optString("code")
                val groupLabel = if (row.optString("strategy") == "combined_limitup_watch") "综合盘后组"
                    else groups[row.optString("group")] ?: row.optString("group")
                box.addView(label("${row.optString("date")} · $groupLabel", 12f))
                box.addView(label("${row.optString("name")}  $code", 16f, true).apply {
                    setOnClickListener { selectedCode = code; showTab(2) }
                })
                box.addView(label(row.optString("reason"), 13f))
                if (row.optString("trigger").isNotBlank()) box.addView(label("介入条件：${row.optString("trigger")}", 12f))
                if (row.optString("invalid").isNotBlank()) box.addView(label("失效条件：${row.optString("invalid")}", 12f))
                val performance = label("查询原始参考价后1/3/5/10/20/30交易日价格表现", 12f); box.addView(performance)
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
            if (audit.length() > 0 && requestedOffset == 0) box.addView(label("待补证历史关注："+
                (0 until audit.length()).joinToString("、") { audit.optJSONObject(it)?.optString("name").orEmpty() }, 12f))
            offset = loaded
            more.visibility = if (data.optBoolean("has_more")) View.VISIBLE else View.GONE
        }
        }
        parent.addView(action("刷新推荐记录") { load(false) })
        more.setOnClickListener { load(true) }
        parent.addView(more)
        load(false)
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
