package ledger.porch.tv.ui.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.tv.material3.Text
import ledger.porch.tv.data.dto.Folded
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvType

@Composable
fun FoldedLine(folded: Folded, modifier: Modifier = Modifier) {
    val parts = mutableListOf<String>()
    if (folded.carsPassed > 0) parts += "${folded.carsPassed} cars passed"
    if (folded.activity > 0) parts += "${folded.activity} other motion"
    if (parts.isEmpty()) return
    Text(
        text = parts.joinToString(" · "),
        style = TvType.Caption,
        color = TvColors.Muted,
        modifier = modifier,
    )
}
