package ledger.porch.tv.data.dto

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class GoldenDtoTest {
    @OptIn(ExperimentalSerializationApi::class)
    private val json =
        Json {
            ignoreUnknownKeys = true
            namingStrategy = JsonNamingStrategy.SnakeCase
        }

    private fun resource(name: String): String = requireNotNull(javaClass.classLoader?.getResource(name)).readText()

    @Test
    fun `golden visit list decodes`() {
        val list = json.decodeFromString<VisitList>(resource("visit_list.json"))
        assertEquals("demo", list.houseId)
        assertEquals(2, list.folded.carsPassed)
        assertEquals(0, list.folded.activity)
        assertEquals(5, list.cards.size)
        assertTrue(list.cards.any { card -> "Box for Priya Shah" in card.facts })
        assertTrue(
            list.cards.all { card ->
                card.heroUrl == null || card.heroUrl.startsWith("/v1/media/")
            },
        )
    }

    @Test
    fun `golden visit detail decodes`() {
        val detail = json.decodeFromString<VisitDetail>(resource("visit_detail.json"))
        assertEquals("delivery", detail.kind)
        assertNotNull(detail.box)
        assertTrue(detail.trace.isNotEmpty())
    }
}
