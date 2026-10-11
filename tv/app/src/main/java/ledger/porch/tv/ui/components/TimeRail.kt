package ledger.porch.tv.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.focusRestorer
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.tv.material3.Border
import androidx.tv.material3.ClickableSurfaceDefaults
import androidx.tv.material3.Surface
import androidx.tv.material3.Text
import ledger.porch.tv.data.dto.VisitCard
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvFocus
import ledger.porch.tv.ui.theme.TvSpacing
import ledger.porch.tv.ui.theme.TvType

private fun glyphColor(kind: String): Color =
    when (kind) {
        "delivery" -> TvColors.Amber
        "visitor" -> TvColors.Sage
        "car_stopped" -> TvColors.Terracotta
        "box_gone" -> TvColors.Terracotta
        else -> TvColors.Muted
    }

@Composable
fun TimeRail(
    cards: List<VisitCard>,
    selectedId: String?,
    onSelect: (String) -> Unit,
    onUp: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val listState = rememberLazyListState()
    val selectedIndex = cards.indexOfFirst { it.id == selectedId }
    LaunchedEffect(selectedIndex) {
        if (selectedIndex >= 0) listState.animateScrollToItem(selectedIndex)
    }
    LazyRow(
        state = listState,
        horizontalArrangement = Arrangement.spacedBy(TvSpacing.S),
        modifier =
            modifier
                .focusRestorer()
                .onPreviewKeyEvent { event ->
                    val up =
                        event.type == KeyEventType.KeyDown &&
                            event.key == Key.DirectionUp
                    if (up) onUp()
                    up
                },
    ) {
        itemsIndexed(cards, key = { _, card -> card.id }) { _, card ->
            RailChip(card = card, selected = card.id == selectedId, onSelect = onSelect)
        }
    }
}

@Composable
private fun RailChip(
    card: VisitCard,
    selected: Boolean,
    onSelect: (String) -> Unit,
) {
    Surface(
        onClick = { onSelect(card.id) },
        shape = ClickableSurfaceDefaults.shape(RoundedCornerShape(TvSpacing.S)),
        colors =
            ClickableSurfaceDefaults.colors(
                containerColor =
                    if (selected) TvColors.Paper else TvColors.Surface,
                contentColor = if (selected) TvColors.Ink else TvColors.Paper,
                focusedContainerColor = TvColors.Paper,
                focusedContentColor = TvColors.Ink,
            ),
        scale = ClickableSurfaceDefaults.scale(focusedScale = TvFocus.SCALE),
        border =
            ClickableSurfaceDefaults.border(
                focusedBorder =
                    Border(BorderStroke(TvFocus.border, TvColors.Amber)),
            ),
        modifier =
            Modifier.onFocusChanged { focus ->
                if (focus.isFocused) onSelect(card.id)
            },
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(TvSpacing.S),
        ) {
            Box(
                modifier =
                    Modifier
                        .size(TvSpacing.S)
                        .clip(CircleShape)
                        .background(glyphColor(card.kind)),
            )
            Text(
                text = "${card.span} · ${card.title}",
                style = TvType.Caption,
                modifier = Modifier.padding(start = TvSpacing.S),
            )
        }
    }
}
