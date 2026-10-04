package com.robin.stock

object WatchlistQuotePolicy {
    private const val RESUME_REFRESH_GAP_MS = 5_000L

    fun ageSeconds(savedAtMillis: Long, nowMillis: Long): Long? {
        if (savedAtMillis <= 0L || nowMillis < savedAtMillis) return null
        return (nowMillis - savedAtMillis) / 1_000L
    }

    fun ageText(ageSeconds: Long?): String = when {
        ageSeconds == null -> "时间未知"
        ageSeconds < 5L -> "刚刚"
        ageSeconds < 60L -> "${ageSeconds}秒前"
        ageSeconds < 3_600L -> "${ageSeconds / 60L}分钟前"
        ageSeconds < 86_400L -> "${ageSeconds / 3_600L}小时前"
        else -> "${ageSeconds / 86_400L}天前"
    }

    fun shouldRefreshOnResume(lastRequestElapsedMs: Long, nowElapsedMs: Long): Boolean =
        lastRequestElapsedMs <= 0L || nowElapsedMs - lastRequestElapsedMs >= RESUME_REFRESH_GAP_MS

    fun shouldRunFollowUp(
        refreshing: Boolean,
        alreadyFollowed: Boolean,
        isForeground: Boolean,
        currentTab: Int,
        expectedGeneration: Int,
        currentGeneration: Int,
    ): Boolean = refreshing && !alreadyFollowed && isForeground && currentTab == 1 &&
        expectedGeneration == currentGeneration
}
