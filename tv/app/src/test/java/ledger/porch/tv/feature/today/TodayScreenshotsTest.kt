package ledger.porch.tv.feature.today

import android.graphics.drawable.ColorDrawable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.test.ext.junit.runners.AndroidJUnit4
import coil3.ImageLoader
import coil3.SingletonImageLoader
import coil3.annotation.DelicateCoilApi
import coil3.test.FakeImageLoaderEngine
import coil3.test.default
import com.github.takahirom.roborazzi.captureRoboImage
import ledger.porch.tv.data.dto.Folded
import ledger.porch.tv.data.dto.VisitCard
import ledger.porch.tv.ui.theme.PorchTheme
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvSpacing
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

private fun card(
    id: String,
    kind: String,
    title: String,
    span: String,
    facts: List<String> = emptyList(),
    description: String = "",
    recipientId: String? = null,
    provenance: String = "replay",
    hero: Boolean = true,
) = VisitCard(
    id = id,
    kind = kind,
    startMs = 1,
    endMs = 2,
    title = title,
    span = span,
    facts = facts,
    description = description,
    heroUrl = if (hero) "http://test/media/$id.jpg" else null,
    clipUrl = null,
    recipientId = recipientId,
    blocksDoor = false,
    claimedBy = null,
    provenance = provenance,
    version = 1,
)

internal val PRIYA =
    card(
        id = "c1",
        kind = "delivery",
        title = "Delivery",
        span = "11:05 to 11:06 am",
        facts = listOf("Box for Priya Shah", "Rain likely by 4:00 pm"),
        description = "A box was left at the door.",
        recipientId = "priya",
    )

internal val JO =
    card(
        id = "c2",
        kind = "delivery",
        title = "Delivery",
        span = "3:20 pm",
        facts = listOf("Box for Jo Lindqvist", "Leaning on the door", "Rain likely by 4:00 pm"),
        description = "A box was left at the door.",
        recipientId = "jo",
    )

internal val VISITOR =
    card(
        id = "c3",
        kind = "visitor",
        title = "Visitor",
        span = "1:30 pm",
        description = "Someone came to the door.",
    )

internal val STOPPED =
    card(
        id = "c4",
        kind = "car_stopped",
        title = "Car stopped",
        span = "5:45 to 5:51 pm",
        facts = listOf("Stopped 6 min"),
        description = "A car stopped outside for 6 min.",
    )

internal val GONE =
    card(
        id = "c5",
        kind = "box_gone",
        title = "Box gone",
        span = "7:10 pm",
        facts = listOf("Box for Priya Shah"),
        description = "A box that was at the door is gone.",
    )

internal val OWN =
    card(
        id = "c6",
        kind = "delivery",
        title = "Delivery",
        span = "9:15 am",
        facts = listOf("Box for Priya Shah"),
        description = "A box was left at the door.",
        recipientId = "priya",
        provenance = "own",
    )

internal fun sampleCards() = listOf(PRIYA, JO, VISITOR, STOPPED, GONE)

@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w1920dp-h1080dp-tvdpi")
class TodayScreenshotsTest {
    @get:Rule
    val composeRule = createComposeRule()

    @OptIn(DelicateCoilApi::class)
    @Before
    fun fakeImages() {
        val engine =
            FakeImageLoaderEngine
                .Builder()
                .default(ColorDrawable(android.graphics.Color.rgb(110, 128, 148)))
                .build()
        SingletonImageLoader.setUnsafe { context ->
            ImageLoader.Builder(context).components { add(engine) }.build()
        }
    }

    private fun today(
        cards: List<VisitCard>,
        selectedId: String? = null,
        offline: Boolean = false,
        folded: Folded = Folded(carsPassed = 2, activity = 0),
    ): @Composable () -> Unit =
        {
            PorchTheme {
                Column(
                    modifier =
                        Modifier
                            .fillMaxSize()
                            .background(TvColors.Bg)
                            .padding(
                                horizontal = TvSpacing.OverscanH,
                                vertical = TvSpacing.OverscanV,
                            ),
                ) {
                    TodayContent(
                        cards = cards,
                        folded = folded,
                        selectedId = selectedId ?: cards.firstOrNull()?.id,
                        offline = offline,
                        day = "2026-06-01",
                        onSelect = {},
                        onClaim = {},
                        onOpenDetail = { _, _ -> },
                    )
                }
            }
        }

    @Test
    fun `delivery matched priya`() {
        composeRule.setContent(today(sampleCards(), selectedId = PRIYA.id))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/today_priya.png")
    }

    @Test
    fun `delivery leaning door rain jo`() {
        composeRule.setContent(today(sampleCards(), selectedId = JO.id))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/today_jo.png")
    }

    @Test
    fun `visitor`() {
        composeRule.setContent(today(sampleCards(), selectedId = VISITOR.id))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/today_visitor.png")
    }

    @Test
    fun `car stopped`() {
        composeRule.setContent(today(sampleCards(), selectedId = STOPPED.id))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/today_car_stopped.png")
    }

    @Test
    fun `box gone`() {
        composeRule.setContent(today(sampleCards(), selectedId = GONE.id))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/today_box_gone.png")
    }

    @Test
    fun `empty day`() {
        composeRule.setContent(today(emptyList()))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/today_empty.png")
    }

    @Test
    fun `offline banner`() {
        composeRule.setContent(today(sampleCards(), offline = true))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/today_offline.png")
    }

    @Test
    fun `own footage badge`() {
        composeRule.setContent(today(listOf(OWN), selectedId = OWN.id))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/today_own_footage.png")
    }
}

@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w1280dp-h720dp-tvdpi")
class TodayScreenshots720Test {
    @get:Rule
    val composeRule = createComposeRule()

    @OptIn(DelicateCoilApi::class)
    @Before
    fun fakeImages() {
        val engine =
            FakeImageLoaderEngine
                .Builder()
                .default(ColorDrawable(android.graphics.Color.rgb(110, 128, 148)))
                .build()
        SingletonImageLoader.setUnsafe { context ->
            ImageLoader.Builder(context).components { add(engine) }.build()
        }
    }

    @Test
    fun `delivery leaning door rain jo at 720p`() {
        composeRule.setContent {
            PorchTheme {
                Column(
                    modifier =
                        Modifier
                            .fillMaxSize()
                            .background(TvColors.Bg)
                            .padding(vertical = TvSpacing.OverscanV),
                ) {
                    TodayContent(
                        cards = sampleCards(),
                        folded = Folded(carsPassed = 2, activity = 0),
                        selectedId = JO.id,
                        day = "2026-06-01",
                        offline = false,
                        onSelect = {},
                        onClaim = {},
                        onOpenDetail = { _, _ -> },
                    )
                }
            }
        }
        composeRule.onRoot().captureRoboImage("src/test/screenshots/today_jo_720.png")
    }
}
