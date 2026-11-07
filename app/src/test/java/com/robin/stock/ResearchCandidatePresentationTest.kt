package com.robin.stock

import org.junit.Assert.assertEquals
import org.junit.Test

class ResearchCandidatePresentationTest {
    @Test fun pendingIntegratedCandidateCannotBeUpgradedByServerLabel() {
        assertEquals("待综合观察", ResearchCandidatePresentation.qualification(
            "combined_pair", "pending_integrated_review_not_final", false, false, "最终研究双标"))
    }

    @Test fun finalLabelRequiresCompletedResearchAndExplicitFinalStatus() {
        assertEquals("待综合观察", ResearchCandidatePresentation.qualification(
            "combined_pair", "final_integrated_pair", false, false, "最终研究双标"))
        assertEquals("最终研究双标", ResearchCandidatePresentation.qualification(
            "combined_pair", "final_integrated_pair", false, true, "最终研究双标"))
    }

    @Test fun convertsUtcAndOffsetTimestampsToBeijing() {
        assertEquals("2026-11-07 06:42", ResearchCandidatePresentation.beijingTime("2026-11-06T22:42:00Z"))
        assertEquals("2026-11-06 15:00", ResearchCandidatePresentation.beijingTime("2026-11-06T15:00:00+08:00"))
    }
}
