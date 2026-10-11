package ledger.porch.tv.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.tv.material3.Text
import coil3.compose.AsyncImage
import ledger.porch.tv.data.dto.VisitCard
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvSpacing
import ledger.porch.tv.ui.theme.TvType

@Composable
fun VisitHero(
    card: VisitCard,
    primaryFocus: FocusRequester,
    onClaim: () -> Unit,
    onNotMine: () -> Unit,
    onPlayClip: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier =
            modifier
                .clip(RoundedCornerShape(TvSpacing.M))
                .background(TvColors.Paper)
                .padding(TvSpacing.L),
        verticalArrangement = Arrangement.spacedBy(TvSpacing.M),
    ) {
        Row(
            verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.spacedBy(TvSpacing.M),
        ) {
            Text(text = card.title, style = TvType.Title, color = TvColors.Ink)
            Text(
                text = card.span,
                style = TvType.Body,
                color = TvColors.Ink,
                modifier = Modifier.weight(1f),
            )
            if (card.provenance == "own") {
                OwnFootageBadge()
            }
        }
        AsyncImage(
            model = card.heroUrl,
            contentDescription = card.title,
            contentScale = ContentScale.Crop,
            modifier =
                Modifier
                    .fillMaxWidth()
                    .aspectRatio(16f / 9f)
                    .clip(RoundedCornerShape(TvSpacing.S))
                    .background(TvColors.Ink),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(TvSpacing.S)) {
            card.facts.forEach { fact -> FactChip(fact) }
        }
        Text(
            text = card.description,
            style = TvType.Body,
            color = TvColors.Ink,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        HeroActions(
            card = card,
            primaryFocus = primaryFocus,
            onClaim = onClaim,
            onNotMine = onNotMine,
            onPlayClip = onPlayClip,
        )
    }
}

@Composable
private fun HeroActions(
    card: VisitCard,
    primaryFocus: FocusRequester,
    onClaim: () -> Unit,
    onNotMine: () -> Unit,
    onPlayClip: () -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(TvSpacing.M)) {
        TvAction(
            label = "It's mine",
            enabled = card.recipientId != null && card.claimedBy == null,
            onClick = onClaim,
            modifier = Modifier.focusRequester(primaryFocus),
        )
        TvAction(label = "Not mine", enabled = false, onClick = onNotMine)
        TvAction(
            label = "Play clip",
            enabled = card.clipUrl != null,
            onClick = onPlayClip,
        )
    }
}
