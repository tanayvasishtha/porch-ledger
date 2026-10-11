package ledger.porch.tv.data

import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class VisitRepositoryTest {
    @get:Rule
    val tempFolder = TemporaryFolder()

    @OptIn(ExperimentalSerializationApi::class)
    private val json = Json {
        ignoreUnknownKeys = true
        namingStrategy = JsonNamingStrategy.SnakeCase
    }

    private fun api(
        handler: suspend io.ktor.client.engine.mock.MockRequestHandleScope.(
            io.ktor.client.request.HttpRequestData,
        ) -> io.ktor.client.request.HttpResponseData,
    ): ApiClient {
        val http = HttpClient(MockEngine(handler)) {
            install(ContentNegotiation) { json(json) }
        }
        return ApiClient(http, baseUrl = "http://test", houseKey = "")
    }

    private fun store(scope: CoroutineScope) = PreferenceDataStoreFactory.create(
        scope = scope,
        produceFile = { File(tempFolder.root, "visits.preferences_pb") },
    )

    @Test
    fun `refresh persists body and resolves relative media urls`() = runTest {
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
        val repo = VisitRepository(api, store(backgroundScope), json)
        val list = repo.refresh("2026-06-01").getOrThrow()
        assertEquals("http://test/v1/media/abc.jpg", list.cards[0].heroUrl)
    }

    @Test
    fun `304 keeps the cached body`() = runTest {
        var calls = 0
        val api = api {
            calls += 1
            if (calls == 1) {
                respond(LIST_JSON, HttpStatusCode.OK, LIST_HEADERS)
            } else {
                respond("", HttpStatusCode.NotModified)
            }
        }
        val repo = VisitRepository(api, store(backgroundScope), json)
        repo.refresh("2026-06-01").getOrThrow()
        val again = repo.refresh("2026-06-01").getOrThrow()
        assertEquals(7, again.version)
    }

    @Test
    fun `offline start replays the last good body`() = runTest {
        var calls = 0
        val api = api {
            calls += 1
            if (calls == 1) {
                respond(LIST_JSON, HttpStatusCode.OK, LIST_HEADERS)
            } else {
                respondError(HttpStatusCode.ServiceUnavailable)
            }
        }
        val store = store(backgroundScope)
        val repo = VisitRepository(api, store, json)
        repo.refresh("2026-06-01").getOrThrow()
        assertTrue(repo.refresh("2026-06-01").isFailure)
        assertNotNull(repo.cachedOrNull())
        val restarted = VisitRepository(api, store, json)
        val warmed = restarted.warmStart()
        assertNotNull(warmed)
        assertEquals(7, warmed!!.version)
        assertTrue(restarted.refresh("2026-06-01").isFailure)
        assertNotNull(restarted.cachedOrNull())
    }

    @Test
    fun `warm start without a file returns null`() = runTest {
        val repo = VisitRepository(api { respondError(HttpStatusCode.OK) }, store(backgroundScope), json)
        assertNull(repo.warmStart())
    }
}
