package ledger.porch.tv.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.tv.material3.Border
import androidx.tv.material3.ClickableSurfaceDefaults
import androidx.tv.material3.Surface
import androidx.tv.material3.Text
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvFocus
import ledger.porch.tv.ui.theme.TvSpacing
import ledger.porch.tv.ui.theme.TvType

@Composable
fun FactChip(
    fact: String,
    modifier: Modifier = Modifier,
) {
    val bg =
        when {
            fact.startsWith("Leaning on") || fact.startsWith("Rain likely") -> {
                TvColors.Terracotta
            }
            fact.startsWith("Box for") -> TvColors.Sage
            else -> TvColors.Muted
        }
    Text(
        text = fact,
        style = TvType.Caption,
        color = TvColors.Ink,
        modifier =
            modifier
                .clip(RoundedCornerShape(TvSpacing.Xs))
                .background(bg)
                .padding(horizontal = TvSpacing.S, vertical = TvSpacing.Xs),
    )
}

@Composable
fun TvAction(
    label: String,
    enabled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        onClick = onClick,
        enabled = enabled,
        shape = ClickableSurfaceDefaults.shape(RoundedCornerShape(TvSpacing.S)),
        colors =
            ClickableSurfaceDefaults.colors(
                containerColor = TvColors.Amber,
                contentColor = TvColors.Ink,
                focusedContainerColor = TvColors.Amber,
                focusedContentColor = TvColors.Ink,
                disabledContainerColor = TvColors.Muted,
                disabledContentColor = TvColors.Ink,
            ),
        scale = ClickableSurfaceDefaults.scale(focusedScale = TvFocus.SCALE),
        border =
            ClickableSurfaceDefaults.border(
                focusedBorder =
                    Border(
                        border = BorderStroke(TvFocus.border, TvColors.Ink),
                    ),
            ),
        modifier = modifier,
    ) {
        Text(
            text = label,
            style = TvType.Body,
            modifier =
                Modifier.padding(horizontal = TvSpacing.L, vertical = TvSpacing.S),
        )
    }
}
