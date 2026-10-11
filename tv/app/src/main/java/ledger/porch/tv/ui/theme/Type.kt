package ledger.porch.tv.ui.theme

import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import ledger.porch.tv.R

private val Fraunces =
    FontFamily(
        Font(R.font.fraunces_regular, FontWeight.Normal),
        Font(R.font.fraunces_semibold, FontWeight.SemiBold),
    )

private val SourceSans =
    FontFamily(
        Font(R.font.sourcesans3_regular, FontWeight.Normal),
        Font(R.font.sourcesans3_semibold, FontWeight.SemiBold),
    )

object TvType {
    val Display =
        TextStyle(
            fontFamily = Fraunces,
            fontWeight = FontWeight.SemiBold,
            fontSize = 48.sp,
        )
    val Title =
        TextStyle(
            fontFamily = Fraunces,
            fontWeight = FontWeight.SemiBold,
            fontSize = 32.sp,
        )
    val Body =
        TextStyle(
            fontFamily = SourceSans,
            fontWeight = FontWeight.Normal,
            fontSize = 22.sp,
        )
    val Caption =
        TextStyle(
            fontFamily = SourceSans,
            fontWeight = FontWeight.Normal,
            fontSize = 18.sp,
        )

    // Time spans sit in rows and columns; tnum keeps the digits aligned.
    val Span =
        Body.copy(fontFeatureSettings = "tnum")
    val SpanSmall =
        Caption.copy(fontFeatureSettings = "tnum")
}
