package ledger.porch.tv.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.tv.material3.Border
import androidx.tv.material3.ClickableSurfaceDefaults
import androidx.tv.material3.Surface
import androidx.tv.material3.Text
import coil3.compose.AsyncImage
import ledger.porch.tv.data.dto.VisitCard
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvFocus
import ledger.porch.tv.ui.theme.TvSpacing
import ledger.porch.tv.ui.theme.TvType

internal fun hasActions(card: VisitCard): Boolean = (card.recipientId != null && card.claimedBy == null) || card.clipUrl != null

// Judges and residents both need to see whose footage a card came from;
// own footage keeps its badge next to the title instead.
internal fun sourceLabel(provenance: String): String? =
    when (provenance) {
        "ring" -> "From the Ring doorbell"
        "replay" -> "Synthetic test day"
        else -> null
    }

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun VisitHero(
    card: VisitCard,
    primaryFocus: FocusRequester,
    onOpenDetails: () -> Unit,
    onClaim: () -> Unit,
    onPlayClip: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier =
            modifier
                .clip(RoundedCornerShape(TvSpacing.M))
                .background(TvColors.Paper)
                .padding(TvSpacing.M),
        horizontalArrangement = Arrangement.spacedBy(TvSpacing.L),
    ) {
        Surface(
            onClick = onOpenDetails,
            shape = ClickableSurfaceDefaults.shape(RoundedCornerShape(TvSpacing.S)),
            scale = ClickableSurfaceDefaults.scale(focusedScale = TvFocus.SCALE),
            modifier =
                Modifier
                    .weight(0.58f)
                    .aspectRatio(16f / 9f)
                    .focusRequester(primaryFocus)
                    .semantics { contentDescription = "Open details" },
        ) {
            AsyncImage(
                model = card.heroUrl,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier =
                    Modifier
                        .fillMaxSize()
                        .clip(RoundedCornerShape(TvSpacing.S))
                        .background(TvColors.Ink),
            )
        }
        Column(
            modifier = Modifier.weight(0.42f),
            verticalArrangement = Arrangement.spacedBy(TvSpacing.S),
        ) {
            HeroBody(
                card = card,
                onClaim = onClaim,
                onPlayClip = onPlayClip,
            )
        }
    }
}

@Composable
private fun androidx.compose.foundation.layout.ColumnScope.HeroBody(
    card: VisitCard,
    onClaim: () -> Unit,
    onPlayClip: () -> Unit,
) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            text = card.title,
            style = TvType.Display,
            color = TvColors.Ink,
            modifier = Modifier.weight(1f),
        )
        if (card.provenance == "own") {
            OwnFootageBadge()
        }
    }
    Row(
        verticalAlignment = Alignment.Bottom,
        horizontalArrangement = Arrangement.spacedBy(TvSpacing.M),
    ) {
        Text(text = card.span, style = TvType.Span, color = TvColors.Ink)
        sourceLabel(card.provenance)?.let { label ->
            Text(text = label, style = TvType.Caption, color = TvColors.InkMuted)
        }
    }
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(TvSpacing.S),
        verticalArrangement = Arrangement.spacedBy(TvSpacing.S),
    ) {
        card.facts.forEach { fact -> FactChip(fact) }
    }
    Text(
        text = card.description,
        style = TvType.Body,
        color = TvColors.Ink,
        maxLines = 2,
        overflow = TextOverflow.Ellipsis,
    )
    if (hasActions(card)) {
        HeroActions(
            card = card,
            onClaim = onClaim,
            onPlayClip = onPlayClip,
        )
    }
}

@Composable
private fun HeroActions(
    card: VisitCard,
    onClaim: () -> Unit,
    onPlayClip: () -> Unit,
) {
    val claimable = card.recipientId != null && card.claimedBy == null
    Row(horizontalArrangement = Arrangement.spacedBy(TvSpacing.M)) {
        if (claimable) {
            TvAction(label = "It's mine", enabled = true, onClick = onClaim)
        }
        if (card.clipUrl != null) {
            TvAction(label = "Play clip", enabled = true, onClick = onPlayClip)
        }
    }
}
