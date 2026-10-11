package ledger.porch.tv.feature.today

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import ledger.porch.tv.data.VisitRepository
import ledger.porch.tv.data.dto.VisitList

private const val MAX_BACKOFF_MS = 60_000L

class TodayViewModel(
    private val repo: VisitRepository,
    private val pollMs: Long = 5_000L,
) : ViewModel() {
    private val _state = MutableStateFlow<TodayUiState>(TodayUiState.Loading)
    val state: StateFlow<TodayUiState> = _state.asStateFlow()
    private var selectedId: String? = null

    suspend fun poll() {
        repo.warmStart()?.let(::publish)
        var backoff = pollMs
        while (true) {
            val result = repo.refresh(day = null)
            result.fold(
                onSuccess = { list ->
                    publish(list)
                    backoff = pollMs
                },
                onFailure = { error ->
                    val cached = repo.cachedOrNull()
                    _state.value =
                        if (cached != null) {
                            TodayUiState.Offline(cached.cards, cached.folded)
                        } else {
                            TodayUiState.Error(
                                error.message ?: "Could not reach the porch ledger.",
                            )
                        }
                    backoff = (backoff * 2).coerceAtMost(MAX_BACKOFF_MS)
                },
            )
            delay(backoff)
        }
    }

    fun select(id: String) {
        selectedId = id
        val current = _state.value
        if (current is TodayUiState.Ready) {
            _state.value = current.copy(selectedId = id)
        }
    }

    fun claim(id: String, residentId: String) {
        optimisticClaim(id, residentId)
        viewModelScope.launch {
            repo.claim(id, residentId)
            // Reconcile either way: cache now reflects the server or the
            // unchanged pre-claim state.
            repo.cachedOrNull()?.let(::publish)
        }
    }

    private fun optimisticClaim(id: String, residentId: String) {
        val current = _state.value
        if (current is TodayUiState.Ready) {
            _state.value =
                current.copy(
                    cards =
                        current.cards.map {
                            if (it.id == id) it.copy(claimedBy = residentId) else it
                        },
                )
        }
    }

    private fun publish(list: VisitList) {
        val selected =
            list.cards.firstOrNull { it.id == selectedId }?.id
                ?: list.cards.firstOrNull()?.id.also { selectedId = it }
        _state.value =
            TodayUiState.Ready(
                cards = list.cards,
                selectedId = selected,
                folded = list.folded,
            )
    }
}
