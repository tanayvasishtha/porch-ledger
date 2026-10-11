package ledger.porch.tv.data

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.flow.first
import kotlinx.serialization.json.Json
import ledger.porch.tv.data.dto.ResidentOut
import ledger.porch.tv.data.dto.VisitCard
import ledger.porch.tv.data.dto.VisitDetail
import ledger.porch.tv.data.dto.VisitList

private val KEY_BODY = stringPreferencesKey("visit_list_body")

class VisitRepository(
    private val api: ApiClient,
    private val store: DataStore<Preferences>,
    private val json: Json,
) {
    private var etag: String? = null
    private var cached: VisitList? = null

    suspend fun warmStart(): VisitList? {
        cached?.let { return withResolvedMedia(it) }
        val raw = store.data.first()[KEY_BODY] ?: return null
        cached = runCatching { json.decodeFromString<VisitList>(raw) }.getOrNull()
        return cached?.let(::withResolvedMedia)
    }

    suspend fun refresh(day: String?): Result<VisitList> = runCatching {
        when (val response = api.visits(day, etag)) {
            is VisitsResponse.NotModified -> cached ?: error("304 without a cached body")
            is VisitsResponse.Fresh -> {
                etag = response.etag
                cached = response.body
                store.edit { prefs -> prefs[KEY_BODY] = json.encodeToString(response.body) }
                response.body
            }
        }
    }.map(::withResolvedMedia)

    suspend fun detail(visitId: String): Result<VisitDetail> =
        runCatching { api.detail(visitId) }.map { detail ->
            detail.copy(
                heroUrl = resolve(detail.heroUrl),
                clipUrl = resolve(detail.clipUrl),
            )
        }

    suspend fun claim(visitId: String, residentId: String): Result<VisitCard> =
        runCatching { api.claim(visitId, residentId) }.map { card ->
            cached = cached?.let { list ->
                list.copy(cards = list.cards.map { if (it.id == card.id) card else it })
            }
            card
        }

    suspend fun residents(): Result<List<ResidentOut>> = runCatching {
        api.residents()
    }

    fun cachedOrNull(): VisitList? = cached?.let(::withResolvedMedia)

    private fun withResolvedMedia(list: VisitList): VisitList = list.copy(
        cards = list.cards.map { card ->
            card.copy(heroUrl = resolve(card.heroUrl), clipUrl = resolve(card.clipUrl))
        },
    )

    private fun resolve(url: String?): String? =
        if (url != null && url.startsWith("/")) api.baseUrl.trimEnd('/') + url else url
}
