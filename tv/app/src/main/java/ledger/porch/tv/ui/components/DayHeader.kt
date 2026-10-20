package ledger.porch.tv.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.tv.material3.Text
import ledger.porch.tv.data.dto.VisitCard
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvSpacing
import ledger.porch.tv.ui.theme.TvType
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException
import java.util.Locale

private val DAY_FORMAT = DateTimeFormatter.ofPattern("EEEE, MMMM d", Locale.US)

// Singular and plural phrasing per card kind, in the order a resident scans
// for: their boxes first, then people, then cars.
private val KIND_PHRASES =
    listOf(
        Triple("delivery", "delivery", "deliveries"),
        Triple("visitor", "visitor", "visitors"),
        Triple("car_stopped", "car stopped", "cars stopped"),
        Triple("box_gone", "box taken in", "boxes taken in"),
    )

/** "2 deliveries, 1 visitor and 1 car stopped so far." from the day's cards. */
fun daySummary(cards: List<VisitCard>): String {
    val parts =
        KIND_PHRASES.mapNotNull { (kind, one, many) ->
            val count = cards.count { it.kind == kind }
            when (count) {
                0 -> null
                1 -> "1 $one"
                else -> "$count $many"
            }
        }
    if (parts.isEmpty()) return "Quiet at the door so far."
    val joined = if (parts.size == 1) parts.single() else parts.dropLast(1).joinToString(", ") + " and " + parts.last()
    return "$joined so far."
}

/** "Tuesday, October 20" for an ISO day; the raw string if it does not parse. */
fun dayTitle(isoDay: String): String =
    try {
        LocalDate.parse(isoDay).format(DAY_FORMAT)
    } catch (_: DateTimeParseException) {
        isoDay
    }

@Composable
fun DayHeader(
    day: String,
    cards: List<VisitCard>,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier,
        verticalAlignment = Alignment.Bottom,
        horizontalArrangement = Arrangement.spacedBy(TvSpacing.L),
    ) {
        Text(text = dayTitle(day), style = TvType.Title, color = TvColors.Paper)
        Text(text = daySummary(cards), style = TvType.Body, color = TvColors.Muted)
    }
}
