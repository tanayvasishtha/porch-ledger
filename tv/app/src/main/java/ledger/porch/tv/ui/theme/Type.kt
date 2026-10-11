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

private val Atkinson =
    FontFamily(
        Font(R.font.atkinson_regular, FontWeight.Normal),
        Font(R.font.atkinson_bold, FontWeight.Bold),
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
            fontFamily = Atkinson,
            fontWeight = FontWeight.Normal,
            fontSize = 22.sp,
        )
    val Caption =
        TextStyle(
            fontFamily = Atkinson,
            fontWeight = FontWeight.Normal,
            fontSize = 18.sp,
        )
}
