package com.robin.stock

import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

object ResearchCandidatePresentation {
    private val beijing = ZoneId.of("Asia/Shanghai")
    private val displayTime = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")

    fun qualification(
        taskId: String,
        candidateStatus: String,
        formalBuySignal: Boolean,
        fullResearchCompleted: Boolean,
        serverLabel: String = "",
    ): String {
        if (formalBuySignal) return "正式条件候选"
        if (taskId == "limitup_single") return "打板观察"
        if (taskId == "combined_pair" && fullResearchCompleted &&
            candidateStatus == "final_integrated_pair" && serverLabel == "最终研究双标") {
            return "最终研究双标"
        }
        if (taskId == "combined_pair") return "待综合观察"
        return serverLabel.takeIf { it in setOf("研究观察", "打板观察") } ?: "研究观察"
    }

    fun beijingTime(value: String): String? = try {
        OffsetDateTime.parse(value).atZoneSameInstant(beijing).format(displayTime)
    } catch (_: Exception) {
        null
    }
}
