package ledger.porch.tv.feature.visit

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import ledger.porch.tv.data.VisitRepository
import ledger.porch.tv.data.dto.VisitDetail

sealed interface VisitUiState {
    data object Loading : VisitUiState

    data class Ready(
        val detail: VisitDetail,
    ) : VisitUiState

    data class Error(
        val message: String,
    ) : VisitUiState
}

class VisitViewModel(
    private val repo: VisitRepository,
    private val visitId: String,
) : ViewModel() {
    private val _state = MutableStateFlow<VisitUiState>(VisitUiState.Loading)
    val state: StateFlow<VisitUiState> = _state.asStateFlow()

    suspend fun load() {
        repo.detail(visitId).fold(
            onSuccess = { detail -> _state.value = VisitUiState.Ready(detail) },
            onFailure = { error ->
                _state.value =
                    VisitUiState.Error(error.message ?: "Could not load the visit.")
            },
        )
    }

    fun claim(detail: VisitDetail) {
        val residentId = detail.recipientId ?: return
        _state.value = VisitUiState.Ready(detail.copy(claimedBy = residentId))
        viewModelScope.launch {
            repo.claim(detail.id, residentId).onSuccess { card ->
                val current = _state.value
                if (current is VisitUiState.Ready) {
                    _state.value =
                        VisitUiState.Ready(current.detail.copy(claimedBy = card.claimedBy))
                }
            }
        }
    }
}
