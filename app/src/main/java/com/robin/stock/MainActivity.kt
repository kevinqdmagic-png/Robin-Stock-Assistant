package com.robin.stock

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.graphics.Color
import android.widget.*
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {
    private val apiBase = "https://robin-stock-api-production.up.railway.app"
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (android.os.Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1001)
        }
        val scroll = ScrollView(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36,48,36,48)
            setBackgroundColor(Color.WHITE)
        }
        fun label(t:String,s:Float,b:Boolean=false)=TextView(this).apply {
            text=t; textSize=s; setTextColor(Color.rgb(25,25,25)); setPadding(0,12,0,12)
            if(b) setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        root.addView(label("Robin股票助手",28f,true))
        root.addView(label("Android v0.1 · 可安装测试版",14f))
        root.addView(label("市场扫描",20f,true))
        val marketStatus=label("正在读取全A行情…",16f)
        root.addView(marketStatus)
        val candidateBox=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL }
        root.addView(candidateBox)
        val refresh=Button(this).apply { text="刷新动态候选" }
        root.addView(refresh)
        fun loadMarket(){
            marketStatus.text="正在读取全A行情…"; candidateBox.removeAllViews()
            thread {
                try {
                    val conn=(URL(apiBase+"/api/market").openConnection() as HttpURLConnection).apply { requestMethod="GET"; connectTimeout=15000; readTimeout=70000 }
                    val rc=conn.responseCode
                    val body=(if(rc in 200..299) conn.inputStream else conn.errorStream).bufferedReader().use{it.readText()}
                    if(rc !in 200..299) throw Exception("HTTP "+rc)
                    val data=JSONObject(body)
                    runOnUiThread {
                        if(!data.optBoolean("ok")) marketStatus.text="行情暂不可用："+data.optString("status")
                        else {
                            marketStatus.text="全A "+data.optInt("count")+"只｜上涨 "+data.optInt("advance")+"｜下跌 "+data.optInt("decline")+"｜"+data.optString("source")
                            val arr=data.optJSONArray("candidates")
                            if(arr!=null) for(idx in 0 until minOf(20,arr.length())){
                                val x=arr.getJSONObject(idx)
                                candidateBox.addView(label((idx+1).toString()+". "+x.optString("name")+" "+x.optString("code")+"\n¥"+x.optDouble("price")+"  "+x.optDouble("pct")+"%  量比 "+x.optDouble("volume_ratio")+"  换手 "+x.optDouble("turnover")+"%  分数 "+x.optDouble("score"),15f))
                            }
                        }
                    }
                } catch(ex:Exception) { runOnUiThread { marketStatus.text="云端连接失败："+(ex.message?:"未知错误") } }
            }
        }
        refresh.setOnClickListener{loadMarket()}
        loadMarket()
        root.addView(label("买点观察",20f,true))
        root.addView(label("暂无真实信号。后续接入：低位首次启动 / 分歧转一致 / 超跌转强。",16f))
        root.addView(label("自选股",20f,true))
        val input=EditText(this).apply { hint="输入股票代码，例如 300502"; inputType=2 }
        val prefs=getSharedPreferences("robin", MODE_PRIVATE)
        val saved=TextView(this).apply { textSize=16f; text="已保存："+prefs.getString("watch","暂无") }
        val btn=Button(this).apply { text="保存到自选" }
        btn.setOnClickListener {
            val code=input.text.toString().trim()
            if(code.isNotEmpty()){ prefs.edit().putString("watch",code).apply(); saved.text="已保存：$code" }
        }
        root.addView(input); root.addView(btn); root.addView(saved)
        root.addView(label("分时图",20f,true))
        root.addView(label("分时图接口将在云端行情接入后启用。",16f))
        root.addView(label("这一版先验证 APK 编译、安装、启动、自选保存和通知权限。",15f))
        scroll.addView(root); setContentView(scroll)
    }
}
