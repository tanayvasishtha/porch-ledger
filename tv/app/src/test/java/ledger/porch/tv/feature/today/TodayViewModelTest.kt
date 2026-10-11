package ledger.porch.tv.feature.today

import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import app.cash.turbine.test
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpStatusCode
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import ledger.porch.tv.data.ApiClient
import ledger.porch.tv.data.JSON_HEADERS
import ledger.porch.tv.data.LIST_HEADERS
import ledger.porch.tv.data.LIST_JSON
import ledger.porch.tv.data.VisitRepository
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

private const val CLAIMED_JSON = """
{"id": "v1", "kind": "delivery", "start_ms": 1, "end_ms": 2,
 "title": "Delivery", "span": "11:05 am", "facts": [], "description": "",
 "hero_url": null, "clip_url": null, "recipient_id": "priya",
 "blocks_door": false, "claimed_by": "priya", "provenance": "replay",
 "version": 2}
"""

class TodayViewModelTest {
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
                produceFile = { File(tempFolder.newFolder(), "v.preferences_pb") },
            )
        return VisitRepository(ApiClient(http, baseUrl = "http://test"), store, json)
    }

    @Test
    fun `poll emits ready from the api`() =
        runTest {
            val viewModel =
                TodayViewModel(
                    repo =
                        repo(backgroundScope) {
                            respond(LIST_JSON, HttpStatusCode.OK, LIST_HEADERS)
                        },
                    pollMs = 1_000,
                )
            backgroundScope.launch { viewModel.poll() }
            val scheduler = testScheduler
            viewModel.state.test {
                assertEquals(TodayUiState.Loading, awaitItem())
                val ready = awaitItem()
                assertTrue(ready is TodayUiState.Ready)
                assertEquals(1, (ready as TodayUiState.Ready).cards.size)
                cancelAndIgnoreRemainingEvents()
            }
        }

    @Test
    fun `304 keeps the ready state`() =
        runTest {
            var calls = 0
            val viewModel =
                TodayViewModel(
                    repo =
                        repo(backgroundScope) {
                            calls += 1
                            if (calls == 1) {
                                respond(LIST_JSON, HttpStatusCode.OK, LIST_HEADERS)
                            } else {
                                respond("", HttpStatusCode.NotModified)
                            }
                        },
                    pollMs = 1_000,
                )
            backgroundScope.launch { viewModel.poll() }
            val scheduler = testScheduler
            viewModel.state.test {
                assertEquals(TodayUiState.Loading, awaitItem())
                assertTrue(awaitItem() is TodayUiState.Ready)
                scheduler.advanceTimeBy(2_000)
                expectNoEvents()
                cancelAndIgnoreRemainingEvents()
            }
        }

    @Test
    fun `error falls back to offline with the cached list`() =
        runTest {
            var calls = 0
            val viewModel =
                TodayViewModel(
                    repo =
                        repo(backgroundScope) {
                            calls += 1
                            if (calls == 1) {
                                respond(LIST_JSON, HttpStatusCode.OK, LIST_HEADERS)
                            } else {
                                respondError(HttpStatusCode.ServiceUnavailable)
                            }
                        },
                    pollMs = 1_000,
                )
            backgroundScope.launch { viewModel.poll() }
            val scheduler = testScheduler
            viewModel.state.test {
                assertEquals(TodayUiState.Loading, awaitItem())
                assertTrue(awaitItem() is TodayUiState.Ready)
                scheduler.advanceTimeBy(2_000)
                val offline = awaitItem()
                assertTrue(offline is TodayUiState.Offline)
                assertEquals(1, (offline as TodayUiState.Offline).cards.size)
                cancelAndIgnoreRemainingEvents()
            }
        }

    @Test
    fun `error without cache becomes error state`() =
        runTest {
            val viewModel =
                TodayViewModel(
                    repo =
                        repo(backgroundScope) {
                            respondError(HttpStatusCode.InternalServerError)
                        },
                    pollMs = 1_000,
                )
            backgroundScope.launch { viewModel.poll() }
            val scheduler = testScheduler
            viewModel.state.test {
                assertEquals(TodayUiState.Loading, awaitItem())
                assertTrue(awaitItem() is TodayUiState.Error)
                cancelAndIgnoreRemainingEvents()
            }
        }

    @Test
    fun `claim publishes the updated card`() =
        runTest {
            var calls = 0
            val viewModel =
                TodayViewModel(
                    repo =
                        repo(backgroundScope) {
                            calls += 1
                            when {
                                calls == 1 ->
                                    respond(
                                        LIST_JSON,
                                        HttpStatusCode.OK,
                                        LIST_HEADERS,
                                    )
                                else -> respond(CLAIMED_JSON, HttpStatusCode.OK, JSON_HEADERS)
                            }
                        },
                    pollMs = 60_000,
                )
            backgroundScope.launch { viewModel.poll() }
            val scheduler = testScheduler
            viewModel.state.test {
                assertEquals(TodayUiState.Loading, awaitItem())
                assertTrue(awaitItem() is TodayUiState.Ready)
                val card = (viewModel.state.value as TodayUiState.Ready).cards[0]
                viewModel.claimSelected(card)
                val optimistic = awaitItem() as TodayUiState.Ready
                assertEquals("priya", optimistic.cards[0].claimedBy)
                scheduler.advanceUntilIdle()
                cancelAndIgnoreRemainingEvents()
            }
        }
}
