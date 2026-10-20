package ledger.porch.tv.ui.components

import ledger.porch.tv.data.dto.VisitCard
import org.junit.Assert.assertEquals
import org.junit.Test

class DayHeaderTest {
    private fun card(kind: String) = VisitCard(id = kind + Math.random(), kind = kind, startMs = 0, endMs = 0, title = "", span = "")

    @Test
    fun `summary counts kinds in resident order with plurals`() {
        val cards = listOf(card("visitor"), card("delivery"), card("car_stopped"), card("delivery"))
        assertEquals("2 deliveries, 1 visitor and 1 car stopped so far.", daySummary(cards))
    }

    @Test
    fun `single kind has no list joiner`() {
        assertEquals("1 box taken in so far.", daySummary(listOf(card("box_gone"))))
    }

    @Test
    fun `no cards reads as a quiet day`() {
        assertEquals("Quiet at the door so far.", daySummary(emptyList()))
    }

    @Test
    fun `title formats an iso day and keeps anything else as is`() {
        assertEquals("Tuesday, October 20", dayTitle("2026-10-20"))
        assertEquals("someday", dayTitle("someday"))
    }

    @Test
    fun `source label names ring and synthetic footage only`() {
        assertEquals("From the Ring doorbell", sourceLabel("ring"))
        assertEquals("Synthetic test day", sourceLabel("replay"))
        assertEquals(null, sourceLabel("own"))
    }
}
