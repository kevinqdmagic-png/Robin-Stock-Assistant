package com.robin.stock

import org.json.JSONObject

/** Keep one alert per recommendation/date/level across foreground and background. */
object EntryAlertPolicy {
    fun key(item: JSONObject): String = item.optString("date_cn") + ":" +
        item.optString("id") + ":" + item.optString("level")

    fun pending(payload: JSONObject, previous: String?): List<JSONObject> {
        if (!payload.optBoolean("ok") || !payload.optBoolean("session_live") ||
            payload.optBoolean("stale")) return emptyList()
        val date = payload.optString("date_cn")
        val existing = previous.orEmpty().split("\n").toSet()
        val rows = payload.optJSONArray("alerts") ?: return emptyList()
        return (0 until rows.length()).mapNotNull { rows.optJSONObject(it) }.filter {
            it.optString("date_cn") == date &&
            it.optString("level") == "price_zone" &&
            !it.optBoolean("all_conditions_verified") &&
            it.optString("id").isNotBlank() && it.optString("code").matches(Regex("[0-9]{6}")) &&
            key(it) !in existing
        }.distinctBy { key(it) }
    }

    fun record(previous: String?, alerts: List<JSONObject>): String =
        (previous.orEmpty().split("\n").filter { it.isNotBlank() } + alerts.map { key(it) })
            .distinct().sorted().takeLast(120).joinToString("\n")
}
