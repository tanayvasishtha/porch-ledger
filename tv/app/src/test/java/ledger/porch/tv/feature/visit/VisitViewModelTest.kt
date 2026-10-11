package ledger.porch.tv.feature.visit

import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import ledger.porch.tv.data.ApiClient
import ledger.porch.tv.data.JSON_HEADERS
import ledger.porch.tv.data.VisitRepository
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

private const val DETAIL_JSON = """
{"id": "v1", "kind": "delivery", "start_ms": 1, "end_ms": 2,
 "title": "Delivery", "span": "11:05 am", "facts": ["Box for Priya Shah"],
 "description": "A box was left at the door.", "hero_url": "/v1/media/hero.jpg",
 "clip_url": null, "recipient_id": "priya", "blocks_door": false,
 "claimed_by": null, "provenance": "replay", "version": 1,
 "box": {"x": 0.6, "y": 0.7, "w": 0.12, "h": 0.18, "recipient_id": "priya",
   "recipient_state": "matched", "blocks_door": false},
 "door_overlap": 0.0,
 "door_polygon": [[0.05, 0.35], [0.38, 0.35], [0.38, 0.95], [0.05, 0.95]],
 "trace": [{"tool": "read_label", "ok": true, "latency_ms": 412, "note": "P Shah"}]}
"""

private const val CLAIMED_JSON = """
{"id": "v1", "kind": "delivery", "start_ms": 1, "end_ms": 2,
 "title": "Delivery", "span": "11:05 am", "facts": [], "description": "",
 "hero_url": null, "clip_url": null, "recipient_id": "priya",
 "blocks_door": false, "claimed_by": "priya", "provenance": "replay",
 "version": 2}
"""

class VisitViewModelTest {
    @get:Rule
    val tempFolder = TemporaryFolder()

    @OptIn(ExperimentalSerializationApi::class)
    private val json =
        Json {
            ignoreUnknownKeys = true
            namingStrategy = JsonNamingStrategy.SnakeCase
        }

    private fun repo(
        scope: CoroutineScope,
        handler: suspend MockRequestHandleScope.(HttpRequestData) -> HttpResponseData,
    ): VisitRepository {
        val http =
            HttpClient(MockEngine(handler)) {
                install(ContentNegotiation) { json(json) }
            }
        val store =
            PreferenceDataStoreFactory.create(
                scope = scope,
                produceFile = { File(tempFolder.newFolder(), "visits.preferences_pb") },
            )
        return VisitRepository(ApiClient(http, baseUrl = "http://api"), store, json)
    }

    @Test
    fun `load resolves hero url and holds detail`() =
        runTest {
            val vm =
                VisitViewModel(
                    repo(this) { respond(DETAIL_JSON, headers = JSON_HEADERS) },
                    "v1",
                )
            vm.load()
            val state = vm.state.value
            assertTrue(state is VisitUiState.Ready)
            val detail = (state as VisitUiState.Ready).detail
            assertEquals("http://api/v1/media/hero.jpg", detail.heroUrl)
            assertEquals(4, detail.doorPolygon?.size)
            assertEquals("read_label", detail.trace.first().tool)
        }

    @Test
    fun `claim marks the card`() =
        runTest {
            val vm =
                VisitViewModel(
                    repo(this) { request ->
                        respond(
                            if (request.url.encodedPath.endsWith("/claim")) {
                                CLAIMED_JSON
                            } else {
                                DETAIL_JSON
                            },
                            headers = JSON_HEADERS,
                        )
                    },
                    "v1",
                )
            vm.load()
            val ready = vm.state.value as VisitUiState.Ready
            vm.claim(ready.detail)
            val after = vm.state.value as VisitUiState.Ready
            assertEquals("priya", after.detail.claimedBy)
        }

    @Test
    fun `load error surfaces the message`() =
        runTest {
            val vm =
                VisitViewModel(
                    repo(this) { respond("", io.ktor.http.HttpStatusCode.InternalServerError) },
                    "v1",
                )
            vm.load()
            assertTrue(vm.state.value is VisitUiState.Error)
        }
}
