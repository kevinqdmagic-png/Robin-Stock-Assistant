package com.robin.stock

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MarketRefreshPolicyTest {
    @Test fun preOpenToMorningSessionRefreshesEverythingImmediately() {
        val decision = MarketRefreshPolicy.decide(
            dayOfWeek = 4, hour = 9, minute = 30,
            currentDate = "2026-10-08", sessionDate = "2026-10-08",
            sessionCode = "before_open", serverSaysLive = false, refreshTick = 0,
        )
        assertTrue(decision.clockOpen)
        assertTrue(decision.refreshOverview)
        assertTrue(decision.refreshMarket)
        assertTrue(decision.refreshCandidates)
    }

    @Test fun lunchToAfternoonSessionRefreshesEverythingImmediately() {
        val decision = MarketRefreshPolicy.decide(
            dayOfWeek = 4, hour = 13, minute = 0,
            currentDate = "2026-10-08", sessionDate = "2026-10-08",
            sessionCode = "lunch", serverSaysLive = false, refreshTick = 1,
        )
        assertTrue(decision.refreshOverview)
        assertTrue(decision.refreshMarket)
        assertTrue(decision.refreshCandidates)
    }

    @Test fun confirmedLiveSessionGetsFastCandidatesAndSlowerFullRefresh() {
        val fast = MarketRefreshPolicy.decide(
            4, 10, 0, "2026-10-08", "2026-10-08", "trading", true, 0,
        )
        assertTrue(fast.refreshCandidates)
        assertFalse(fast.refreshMarket)
        assertFalse(fast.refreshOverview)

        val full = MarketRefreshPolicy.decide(
            4, 10, 1, "2026-10-08", "2026-10-08", "trading", true, 2,
        )
        assertTrue(full.refreshCandidates)
        assertTrue(full.refreshMarket)
        assertTrue(full.refreshOverview)
    }

    @Test fun lunchAndHolidayDoNotPollCandidates() {
        val lunch = MarketRefreshPolicy.decide(
            4, 11, 30, "2026-10-08", "2026-10-08", "trading", true, 0,
        )
        assertTrue(lunch.refreshOverview)
        assertFalse(lunch.refreshCandidates)

        val holiday = MarketRefreshPolicy.decide(
            4, 10, 0, "2026-10-01", "2026-10-01", "closed", false, 0,
        )
        assertFalse(holiday.refreshOverview)
        assertFalse(holiday.refreshMarket)
        assertFalse(holiday.refreshCandidates)
    }

    @Test fun breadthMoodUsesCoveredUniverseOnly() {
        assertEquals("偏热", MarketRefreshPolicy.breadthMood(75, 20, 5).label)
        assertEquals("偏冷", MarketRefreshPolicy.breadthMood(20, 75, 5).label)
        assertEquals("均衡", MarketRefreshPolicy.breadthMood(50, 45, 5).label)
        assertNull(MarketRefreshPolicy.breadthMood(0, 0, 0).advancePct)
    }
}
