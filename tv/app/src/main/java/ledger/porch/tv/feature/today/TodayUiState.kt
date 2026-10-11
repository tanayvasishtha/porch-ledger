package ledger.porch.tv.feature.today

import ledger.porch.tv.data.dto.Folded
import ledger.porch.tv.data.dto.VisitCard

sealed interface TodayUiState {
    data object Loading : TodayUiState

    data class Ready(
        val cards: List<VisitCard>,
        val selectedId: String?,
        val folded: Folded,
    ) : TodayUiState

    data class Offline(
        val cards: List<VisitCard>,
        val folded: Folded,
    ) : TodayUiState

    data class Error(
        val message: String,
    ) : TodayUiState
}
