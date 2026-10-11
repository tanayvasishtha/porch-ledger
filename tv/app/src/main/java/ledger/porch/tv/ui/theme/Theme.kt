package ledger.porch.tv.ui.theme

import androidx.compose.runtime.Composable
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.darkColorScheme

private val PorchColors =
    darkColorScheme(
        primary = TvColors.Amber,
        onPrimary = TvColors.Ink,
        secondary = TvColors.Sage,
        onSecondary = TvColors.Ink,
        tertiary = TvColors.Terracotta,
        onTertiary = TvColors.Ink,
        background = TvColors.Bg,
        onBackground = TvColors.Paper,
        surface = TvColors.Surface,
        onSurface = TvColors.Paper,
        surfaceVariant = TvColors.Surface,
        onSurfaceVariant = TvColors.Muted,
        error = TvColors.Terracotta,
        onError = TvColors.Ink,
        border = TvColors.Amber,
        inverseOnSurface = TvColors.Ink,
        inverseSurface = TvColors.Paper,
    )

@Composable
fun PorchTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = PorchColors, content = content)
}
