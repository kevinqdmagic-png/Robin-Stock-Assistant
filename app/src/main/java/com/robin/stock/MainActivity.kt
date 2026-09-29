package com.robin.stock

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.graphics.Color
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {
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
        root.addView(label("云端后台：尚未连接\n全A扫描：等待后台部署\n当前版本不显示伪造实时行情",16f))
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
