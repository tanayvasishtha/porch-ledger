package ledger.porch.tv.data

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import ledger.porch.tv.data.dto.ClaimRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

internal const val LIST_JSON = """
{
  "house_id": "demo", "day": "2026-06-01", "version": 7,
  "cards": [{"id": "v1", "kind": "delivery", "start_ms": 1, "end_ms": 2,
    "title": "Delivery", "span": "11:05 am", "facts": [], "description": "",
    "hero_url": "/v1/media/abc.jpg", "clip_url": null, "recipient_id": "priya",
    "blocks_door": false, "claimed_by": null, "provenance": "replay", "version": 1}],
  "folded": {"cars_passed": 2, "activity": 0}
}
"""


internal val JSON_HEADERS =
    headersOf(HttpHeaders.ContentType to listOf("application/json"))
internal val LIST_HEADERS =
    headersOf(
        HttpHeaders.ContentType to listOf("application/json"),
        HttpHeaders.ETag to listOf("\"v7\""),
    )

internal const val PROBLEM_JSON = """
{"type": "about:blank", "title": "Nope", "status": 401, "detail": "bad key"}
"""

class ApiClientTest {
    @OptIn(ExperimentalSerializationApi::class)
    private val json = Json {
        ignoreUnknownKeys = true
        namingStrategy = JsonNamingStrategy.SnakeCase
    }

    private var lastRequest: HttpRequestData? = null

    private fun api(
        handler: suspend MockRequestHandleScope.(HttpRequestData) -> HttpResponseData,
    ): ApiClient {
        val engine = MockEngine { request ->
            lastRequest = request
            handler(request)
        }
        val http = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        return ApiClient(http, baseUrl = "http://test", houseKey = "", houseId = "demo")
    }

    @Test
    fun `fresh body carries its etag`() = runTest {
        val api = api {
            respond(
                LIST_JSON,
                HttpStatusCode.OK,
                headersOf(
                    HttpHeaders.ContentType to listOf("application/json"),
                    HttpHeaders.ETag to listOf("\"v7\""),
                ),
            )
        }
        val result = api.visits("2026-06-01", null)
        assertTrue(result is VisitsResponse.Fresh)
        val fresh = result as VisitsResponse.Fresh
        assertEquals("\"v7\"", fresh.etag)
        assertEquals(7, fresh.body.version)
        assertEquals(1, fresh.body.cards.size)
        assertEquals("/v1/media/abc.jpg", fresh.body.cards[0].heroUrl)
    }

    @Test
    fun `304 short circuits to NotModified and sends If-None-Match`() = runTest {
        val api = api { respond("", HttpStatusCode.NotModified) }
        val result = api.visits("2026-06-01", "\"v7\"")
        assertEquals(VisitsResponse.NotModified, result)
        assertEquals("\"v7\"", lastRequest?.headers?.get(HttpHeaders.IfNoneMatch))
    }

    @Test
    fun `non 2xx maps problem body to ApiException`() = runTest {
        val api = api {
            respond(
                PROBLEM_JSON,
                HttpStatusCode.Unauthorized,
                headersOf(HttpHeaders.ContentType to listOf("application/problem+json")),
            )
        }
        try {
            api.visits("2026-06-01", null)
            fail("expected ApiException")
        } catch (exc: ApiException) {
            assertEquals(401, exc.status)
            assertEquals("Nope", exc.problem?.title)
            assertEquals("bad key", exc.problem?.detail)
        }
    }

    @Test
    fun `missing visit maps to ApiException`() = runTest {
        val api = api { respondError(HttpStatusCode.NotFound) }
        try {
            api.detail("v-missing")
            fail("expected ApiException")
        } catch (exc: ApiException) {
            assertEquals(404, exc.status)
        }
    }

    @Test
    fun `claim posts the resident id as json`() = runTest {
        val cardJson = """{"id": "v1", "kind": "delivery", "start_ms": 1, "end_ms": 2,
            "title": "Delivery", "span": "11:05 am", "facts": [], "description": "",
            "hero_url": null, "clip_url": null, "recipient_id": "priya",
            "blocks_door": false, "claimed_by": "priya", "provenance": "replay",
            "version": 2}"""
        val api = api {
            respond(cardJson, HttpStatusCode.OK, JSON_HEADERS)
        }
        val card = api.claim("v1", "priya")
        assertEquals("priya", card.claimedBy)
        assertEquals(2, card.version)
        val sent = json.decodeFromString<ClaimRequest>(
            (lastRequest!!.body as TextContent).text,
        )
        assertEquals("priya", sent.residentId)
        assertEquals(ContentType.Application.Json, lastRequest!!.body.contentType)
    }
}
