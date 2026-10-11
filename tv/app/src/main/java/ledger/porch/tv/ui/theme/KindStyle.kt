package ledger.porch.tv.ui.theme

import androidx.compose.ui.graphics.Color

// One place maps visit kinds to their rail dot colour; terracotta stays
// reserved for warning chips.
fun kindDot(kind: String): Color =
    when (kind) {
        "delivery" -> TvColors.Amber
        "visitor" -> TvColors.Sage
        else -> TvColors.Muted
    }
