package ledger.porch.tv.feature.today

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.tv.material3.Text
import coil3.SingletonImageLoader
import coil3.request.ImageRequest
import ledger.porch.tv.data.dto.Folded
import ledger.porch.tv.data.dto.VisitCard
import ledger.porch.tv.ui.components.DayHeader
import ledger.porch.tv.ui.components.FoldedLine
import ledger.porch.tv.ui.components.TimeRail
import ledger.porch.tv.ui.components.VisitHero
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvSpacing
import ledger.porch.tv.ui.theme.TvType

@Composable
fun TodayScreen(
    viewModel: TodayViewModel,
    onOpenDetail: (visitId: String, autoplay: Boolean) -> Unit,
    modifier: Modifier = Modifier,
    focusRail: Boolean = false,
) {
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
                .padding(vertical = TvSpacing.OverscanV),
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
                    day = current.day,
                    onSelect = viewModel::select,
                    onClaim = { card -> viewModel.claimSelected(card) },
                    onOpenDetail = onOpenDetail,
                    focusRail = focusRail,
                )
            is TodayUiState.Offline ->
                TodayContent(
                    cards = current.cards,
                    folded = current.folded,
                    selectedId = null,
                    offline = true,
                    day = current.day,
                    onSelect = viewModel::select,
                    onClaim = { card -> viewModel.claimSelected(card) },
                    onOpenDetail = onOpenDetail,
                    focusRail = focusRail,
                )
        }
    }
}

@Composable
internal fun ColumnScope.TodayContent(
    cards: List<VisitCard>,
    folded: Folded,
    selectedId: String?,
    offline: Boolean,
    onSelect: (String) -> Unit,
    onClaim: (VisitCard) -> Unit,
    onOpenDetail: (String, Boolean) -> Unit,
    focusRail: Boolean = false,
    day: String = "",
) {
    if (day.isNotEmpty()) {
        DayHeader(
            day = day,
            cards = cards,
            modifier = Modifier.padding(horizontal = TvSpacing.OverscanH),
        )
    }
    if (offline) {
        Text(
            text = "Showing the last update. Reconnecting.",
            style = TvType.Caption,
            color = TvColors.Muted,
            modifier = Modifier.padding(horizontal = TvSpacing.OverscanH),
        )
    }
    if (cards.isEmpty()) {
        CenteredLine("Nothing at the door yet today.")
        return
    }
    val selected = cards.firstOrNull { it.id == selectedId } ?: cards.first()
    val context = LocalContext.current
    LaunchedEffect(cards.map { it.heroUrl }) {
        // Warm the image cache so moving along the rail never shows an empty frame.
        val loader = SingletonImageLoader.get(context)
        cards.mapNotNull { it.heroUrl }.forEach { url ->
            loader.enqueue(ImageRequest.Builder(context).data(url).build())
        }
    }
    val heroFocus = remember { FocusRequester() }
    val railFocus = remember { FocusRequester() }
    VisitHero(
        card = selected,
        primaryFocus = heroFocus,
        onOpenDetails = { onOpenDetail(selected.id, false) },
        onClaim = { onClaim(selected) },
        onPlayClip = { onOpenDetail(selected.id, true) },
        modifier =
            Modifier
                .fillMaxWidth()
                .padding(horizontal = TvSpacing.OverscanH)
                .focusProperties { down = railFocus },
    )
    TimeRail(
        cards = cards,
        selectedId = selected.id,
        selectedFocus = railFocus,
        onSelect = onSelect,
        onUp = { heroFocus.requestFocus() },
        modifier = Modifier.fillMaxWidth(),
    )
    FoldedLine(
        folded = folded,
        modifier = Modifier.padding(horizontal = TvSpacing.OverscanH),
    )
    LaunchedEffect(Unit) {
        // Lazy rail items apply after the first frame; wait before asking
        // for focus or the requester is not yet initialized.
        withFrameNanos { }
        // Open details on the hero image is always actionable; the rail
        // only wins when returning from the detail screen.
        if (focusRail) railFocus.requestFocus() else heroFocus.requestFocus()
    }
}

@Composable
private fun CenteredLine(message: String) {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(text = message, style = TvType.Body, color = TvColors.Muted)
    }
}
