package ledger.porch.tv.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.tv.material3.Text
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvSpacing
import ledger.porch.tv.ui.theme.TvType

@Composable
fun OwnFootageBadge(modifier: Modifier = Modifier) {
    Text(
        text = "Our footage, not Ring",
        style = TvType.Caption,
        color = TvColors.Ink,
        modifier =
            modifier
                .clip(RoundedCornerShape(TvSpacing.Xs))
                .background(TvColors.Sage)
                .padding(horizontal = TvSpacing.S, vertical = TvSpacing.Xs),
    )
}
