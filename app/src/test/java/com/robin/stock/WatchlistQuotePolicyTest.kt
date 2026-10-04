package com.robin.stock

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class WatchlistQuotePolicyTest {
    @Test fun cacheAgeIsExplicitAndHumanReadable() {
        assertNull(WatchlistQuotePolicy.ageSeconds(0L, 20_000L))
        assertEquals(65L, WatchlistQuotePolicy.ageSeconds(5_000L, 70_000L))
        assertEquals("刚刚", WatchlistQuotePolicy.ageText(2L))
        assertEquals("59秒前", WatchlistQuotePolicy.ageText(59L))
        assertEquals("2分钟前", WatchlistQuotePolicy.ageText(125L))
        assertEquals("3小时前", WatchlistQuotePolicy.ageText(10_900L))
        assertEquals("2天前", WatchlistQuotePolicy.ageText(180_000L))
        assertEquals("时间未知", WatchlistQuotePolicy.ageText(null))
    }

    @Test fun returningFromBackgroundRefreshesOnlyAfterSmallDebounce() {
        assertTrue(WatchlistQuotePolicy.shouldRefreshOnResume(0L, 1_000L))
        assertFalse(WatchlistQuotePolicy.shouldRefreshOnResume(8_000L, 12_999L))
        assertTrue(WatchlistQuotePolicy.shouldRefreshOnResume(8_000L, 13_000L))
    }

    @Test fun staleFollowUpCannotEscapeWatchlistPage() {
        assertTrue(WatchlistQuotePolicy.shouldRunFollowUp(true, false, true, 1, 7, 7))
        assertFalse(WatchlistQuotePolicy.shouldRunFollowUp(true, false, true, 0, 7, 7))
        assertFalse(WatchlistQuotePolicy.shouldRunFollowUp(true, false, false, 1, 7, 7))
        assertFalse(WatchlistQuotePolicy.shouldRunFollowUp(true, false, true, 1, 7, 8))
        assertFalse(WatchlistQuotePolicy.shouldRunFollowUp(true, true, true, 1, 7, 7))
    }
}
