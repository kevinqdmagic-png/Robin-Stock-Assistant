package com.robin.stock

import org.junit.Assert.assertEquals
import org.junit.Test

class WatchlistPolicyTest {
    @Test fun preservesManualChoicesAndDeduplicatesResearchSeeds() {
        val result = WatchlistPolicy.seed(listOf("600380", "300450"), emptyList(), listOf("300450", "688498"))
        assertEquals(listOf("600380", "300450", "688498"), result.watchlist)
        assertEquals(listOf("300450", "688498"), result.seededCodes)
    }

    @Test fun removedResearchStockStaysRemovedAfterReload() {
        val first = WatchlistPolicy.seed(emptyList(), emptyList(), listOf("300450", "603662"))
        val next = WatchlistPolicy.seed(listOf("603662"), first.seededCodes, listOf("300450", "603662"))
        assertEquals(listOf("603662"), next.watchlist)
    }

    @Test fun newResearchAddsOnlyPreviouslyUnofferedCodes() {
        val result = WatchlistPolicy.seed(listOf("600380"), listOf("300450"), listOf("300450", "002993"))
        assertEquals(listOf("600380", "002993"), result.watchlist)
    }

    @Test fun ignoresInvalidCodesAndPreservesLeadingZeroes() {
        val result = WatchlistPolicy.seed(listOf(" 002130 ", "../123", "１２３４５６"), emptyList(), listOf("002130", "002364"))
        assertEquals(listOf("002130", "002364"), result.watchlist)
    }
}
