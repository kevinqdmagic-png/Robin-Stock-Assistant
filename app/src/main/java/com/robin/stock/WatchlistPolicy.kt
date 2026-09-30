package com.robin.stock

/** Preserve manual choices and remember offered seeds even after the user removes them. */
object WatchlistPolicy {
    private val validCode = Regex("[0-9]{6}")
    data class SeedResult(val watchlist: List<String>, val seededCodes: List<String>)

    fun codes(values: Iterable<String>): List<String> =
        values.map { it.trim() }.filter { validCode.matches(it) }.distinct()

    fun seed(existing: List<String>, offeredBefore: List<String>, defaults: List<String>): SeedResult {
        val seen = codes(offeredBefore)
        val offered = codes(defaults)
        return SeedResult(codes(existing + offered.filter { it !in seen }), codes(seen + offered))
    }
}
