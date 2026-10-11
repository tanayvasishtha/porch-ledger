package ledger.porch.tv.feature.today

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.tv.material3.Text
import ledger.porch.tv.data.dto.Folded
import ledger.porch.tv.data.dto.VisitCard
import ledger.porch.tv.ui.components.FoldedLine
import ledger.porch.tv.ui.components.TimeRail
import ledger.porch.tv.ui.components.VisitHero
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvSpacing
import ledger.porch.tv.ui.theme.TvType

@Composable
fun TodayScreen(viewModel: TodayViewModel, modifier: Modifier = Modifier) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
            viewModel.poll()
        }
    }
    Column(
        modifier =
            modifier
                .fillMaxSize()
                .background(TvColors.Bg)
                .padding(
                    horizontal = TvSpacing.OverscanH,
                    vertical = TvSpacing.OverscanV,
                ),
        verticalArrangement = Arrangement.spacedBy(TvSpacing.M),
    ) {
        when (val current = state) {
            is TodayUiState.Loading -> CenteredLine("Loading the porch…")
            is TodayUiState.Error -> CenteredLine(current.message)
            is TodayUiState.Ready ->
                TodayContent(
                    cards = current.cards,
                    folded = current.folded,
                    selectedId = current.selectedId,
                    offline = false,
                    viewModel = viewModel,
                )
            is TodayUiState.Offline ->
                TodayContent(
                    cards = current.cards,
                    folded = current.folded,
                    selectedId = null,
                    offline = true,
                    viewModel = viewModel,
                )
        }
    }
}

@Composable
private fun ColumnScope.TodayContent(
    cards: List<VisitCard>,
    folded: Folded,
    selectedId: String?,
    offline: Boolean,
    viewModel: TodayViewModel,
) {
    if (offline) {
        Text(
            text = "Showing the last update. Reconnecting.",
            style = TvType.Caption,
            color = TvColors.Muted,
        )
    }
    if (cards.isEmpty()) {
        CenteredLine("Nothing at the door yet today.")
        return
    }
    val selected = cards.firstOrNull { it.id == selectedId } ?: cards.first()
    val heroFocus = remember { FocusRequester() }
    Row(modifier = Modifier.weight(1f)) {
        VisitHero(
            card = selected,
            primaryFocus = heroFocus,
            onClaim = {
                selected.recipientId?.let { viewModel.claim(selected.id, it) }
            },
            onNotMine = {},
            onPlayClip = {},
            modifier = Modifier.weight(0.66f),
        )
        Spacer(modifier = Modifier.weight(0.34f))
    }
    TimeRail(
        cards = cards,
        selectedId = selected.id,
        onSelect = viewModel::select,
        onUp = { heroFocus.requestFocus() },
        modifier = Modifier.fillMaxWidth(),
    )
    FoldedLine(folded = folded)
    LaunchedEffect(Unit) { heroFocus.requestFocus() }
}

@Composable
private fun CenteredLine(message: String) {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(text = message, style = TvType.Body, color = TvColors.Muted)
    }
}
