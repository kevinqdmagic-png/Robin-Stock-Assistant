package com.robin.stock

import android.content.Intent
import android.graphics.Bitmap
import android.os.Build
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class ResearchNavigationTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()

    private fun texts(view: View): List<TextView> =
        (if (view is TextView) listOf(view) else emptyList()) +
            if (view is ViewGroup) (0 until view.childCount).flatMap { texts(view.getChildAt(it)) } else emptyList()

    private fun content(activity: MainActivity) = activity.findViewById<ViewGroup>(android.R.id.content)
    private fun nav(activity: MainActivity): LinearLayout {
        val shell = content(activity).getChildAt(0) as LinearLayout
        return shell.getChildAt(shell.childCount - 1) as LinearLayout
    }
    private fun click(activity: MainActivity, title: String) {
        instrumentation.runOnMainSync {
            val label = texts(content(activity)).first { it.text.toString() == title }
            var target: View = label
            while (!target.isClickable && target.parent is View) target = target.parent as View
            assertTrue("Clickable target for $title", target.performClick())
        }
        instrumentation.waitForIdleSync()
    }
    private fun screenshot(name: String) {
        instrumentation.waitForIdleSync()
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        assertNotNull(bitmap)
        File(instrumentation.targetContext.filesDir, name).outputStream().use {
            assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it))
        }
        bitmap.recycle()
    }

    @Test fun notificationResearchWatchlistDetailAndValidationRemainReachable() {
        val context = instrumentation.targetContext
        if (Build.VERSION.SDK_INT >= 33) instrumentation.uiAutomation.grantRuntimePermission(
            context.packageName, "android.permission.POST_NOTIFICATIONS")
        val activity = instrumentation.startActivitySync(Intent(context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK).putExtra("open_research", true)) as MainActivity
        try {
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                assertEquals(listOf("首页", "自选", "研究", "验证"), texts(nav(activity)).map { it.text.toString() })
                assertTrue(nav(activity).getChildAt(2).isSelected)
                assertTrue(texts(content(activity)).any { it.text.toString() == "每日定时研究成果" })
                assertFalse(texts(content(activity)).any { it.text.toString() == "定时任务中心" })
            }
            screenshot("navigation-research.png")
            click(activity, "验证")
            instrumentation.runOnMainSync {
                assertTrue(texts(content(activity)).any { it.text.toString() == "看上涨比例" })
                assertTrue(texts(content(activity)).any { it.text.toString() == "看平均收益" })
                assertFalse(texts(content(activity)).any { it.text.toString() == "研究历史" })
            }
            screenshot("navigation-validation.png")
            click(activity, "任务状态")
            instrumentation.runOnMainSync {
                assertTrue(texts(content(activity)).any { it.text.toString() == "定时任务中心" })
            }
            click(activity, "自选")
            instrumentation.runOnMainSync {
                texts(content(activity)).filterIsInstance<EditText>().first().setText("600000")
            }
            click(activity, "加入自选")
            click(activity, "推荐理由 / 分时")
            instrumentation.runOnMainSync {
                assertTrue(texts(content(activity)).any { it.text.toString() == "分钟走势" })
                assertEquals(listOf("首页", "自选", "研究", "验证"), texts(nav(activity)).map { it.text.toString() })
            }
            instrumentation.sendKeyDownUpSync(KeyEvent.KEYCODE_BACK)
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync { assertTrue(nav(activity).getChildAt(1).isSelected) }
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
        }
    }
}
