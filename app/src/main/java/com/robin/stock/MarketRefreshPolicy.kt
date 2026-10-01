package com.robin.stock

data class MarketRefreshDecision(
    val clockOpen: Boolean,
    val refreshOverview: Boolean,
    val refreshMarket: Boolean,
    val refreshCandidates: Boolean,
)

data class BreadthMood(val label: String, val advancePct: Double?)

object MarketRefreshPolicy {
    fun decide(
        dayOfWeek: Int,
        hour: Int,
        minute: Int,
        currentDate: String,
        sessionDate: String,
        sessionCode: String,
        serverSaysLive: Boolean,
        refreshTick: Int,
    ): MarketRefreshDecision {
        val minutes = hour * 60 + minute
        val clockOpen = dayOfWeek in 1..5 &&
            (minutes in 570 until 690 || minutes in 780 until 900)
        val changedDay = sessionDate.isNotBlank() && sessionDate != currentDate
        val enteringTrading = clockOpen && sessionCode in setOf("before_open", "lunch", "")
        val leavingTrading = !clockOpen && sessionCode == "trading"
        val periodicOverview = clockOpen && serverSaysLive && refreshTick % 3 == 2
        val refreshCandidates = clockOpen && (serverSaysLive || enteringTrading)
        return MarketRefreshDecision(
            clockOpen = clockOpen,
            refreshOverview = changedDay || enteringTrading || leavingTrading || periodicOverview,
            refreshMarket = refreshCandidates && (enteringTrading || periodicOverview),
            refreshCandidates = refreshCandidates,
        )
    }

    fun breadthMood(advance: Int, decline: Int, flat: Int): BreadthMood {
        val total = advance + decline + flat
        if (total <= 0) return BreadthMood("待核验", null)
        val pct = advance * 100.0 / total
        val label = when {
            pct >= 70 -> "偏热"
            pct >= 55 -> "偏强"
            pct <= 30 -> "偏冷"
            pct <= 45 -> "偏弱"
            else -> "均衡"
        }
        return BreadthMood(label, pct)
    }
}
