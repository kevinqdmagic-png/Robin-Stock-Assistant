package com.robin.stock

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkerParameters
import androidx.work.WorkManager
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

/**
 * Best-effort periodic polling, not instant server push. Android may defer work
 * under battery restrictions or Doze. Reports are only notified when their
 * published IDs actually change.
 */
class ResearchNotificationWorker(context: Context, params: WorkerParameters) :
    CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val prefs = applicationContext.getSharedPreferences("robin", Context.MODE_PRIVATE)
        val connection = try {
            (URL("https://robin-stock-api-production.up.railway.app/api/tasks")
                .openConnection() as HttpURLConnection).apply {
                connectTimeout = 10000
                readTimeout = 10000
                requestMethod = "GET"
            }
        } catch (_: Exception) {
            return Result.retry()
        }
        val body = try {
            if (connection.responseCode !in 200..299) return Result.retry()
            connection.inputStream.bufferedReader().use { it.readText() }
        } catch (_: Exception) {
            return Result.retry()
        } finally {
            connection.disconnect()
        }
        val payload = try { JSONObject(body) } catch (_: Exception) { return Result.retry() }
        if (!payload.optBoolean("ok")) return Result.retry()
        val rows = payload.optJSONArray("items") ?: return Result.retry()
        val ids = setOf("market_review", "volume_price", "low_dragon",
            "combined_pair", "limitup_single", "early_pair", "late_pair")
        val previous = prefs.getString("notified_research_versions", null)
        val old = try { JSONObject(previous ?: "{}") } catch (_: Exception) { JSONObject() }
        val updated = JSONObject()
        val changed = mutableListOf<String>()
        for (i in 0 until rows.length()) {
            val task = rows.optJSONObject(i) ?: continue
            val id = task.optString("id")
            if (id !in ids) continue
            val reportId = task.optJSONObject("latest_report")?.optString("id").orEmpty()
            if (reportId.isBlank()) continue
            updated.put(id, reportId)
            if (previous != null && old.has(id) && old.optString(id) != reportId) {
                changed.add(task.optString("title", id))
            }
        }
        if (updated.length() == 0) return Result.success()
        // Don't silently consume updates while notifications are disallowed.
        val canNotify = Build.VERSION.SDK_INT < 33 ||
            applicationContext.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED
        if (changed.isNotEmpty() && !canNotify) return Result.success()
        if (!prefs.edit().putString("notified_research_versions", updated.toString()).commit()) {
            return Result.retry()
        }
        if (changed.isNotEmpty()) notifyResearch(changed)
        return Result.success()
    }

    private fun notifyResearch(titles: List<String>) {
        val manager = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = "robin_research_updates"
        manager.createNotificationChannel(NotificationChannel(
            channel, "股票研究报告更新", NotificationManager.IMPORTANCE_DEFAULT))
        val intent = Intent(applicationContext, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("open_research", true)
        }
        val pending = PendingIntent.getActivity(applicationContext, 991, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val detail = titles.distinct().joinToString("、")
        manager.notify(991, NotificationCompat.Builder(applicationContext, channel)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("股票助手有新研究报告")
            .setContentText(detail)
            .setStyle(NotificationCompat.BigTextStyle().bigText(detail))
            .setContentIntent(pending)
            .setAutoCancel(true)
            .build())
    }

    companion object {
        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED).build()
            val work = PeriodicWorkRequestBuilder<ResearchNotificationWorker>(
                30, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "robin_research_notification_poll",
                ExistingPeriodicWorkPolicy.KEEP, work)
        }
    }
}
