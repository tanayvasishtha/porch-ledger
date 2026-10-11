package ledger.porch.tv.feature.visit

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
import ledger.porch.tv.data.dto.BoxOut
import ledger.porch.tv.data.dto.ToolCallOut
import ledger.porch.tv.data.dto.VisitDetail
import ledger.porch.tv.ui.theme.PorchTheme
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvSpacing
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

private fun detail(
    id: String,
    kind: String,
    title: String,
    recipientId: String? = null,
    box: BoxOut? = null,
    polygon: List<List<Float>>? = null,
    trace: List<ToolCallOut> = emptyList(),
) = VisitDetail(
    id = id,
    kind = kind,
    startMs = 1,
    endMs = 2,
    title = title,
    span = "11:05 to 11:06 am",
    facts = listOf("Box for Priya Shah", "Rain likely by 4:00 pm"),
    description = "A box was left at the door.",
    heroUrl = "http://test/media/$id.jpg",
    clipUrl = null,
    recipientId = recipientId,
    blocksDoor = box?.blocksDoor,
    claimedBy = null,
    provenance = "replay",
    version = 1,
    box = box,
    doorPolygon = polygon,
    trace = trace,
)

private val DOOR = listOf(listOf(0.05f, 0.35f), listOf(0.38f, 0.35f), listOf(0.38f, 0.95f), listOf(0.05f, 0.95f))

internal val PRIYA_DETAIL =
    detail(
        id = "v1",
        kind = "delivery",
        title = "Delivery",
        recipientId = "priya",
        box = BoxOut(x = 0.6f, y = 0.7f, w = 0.12f, h = 0.18f, recipientId = "priya", recipientState = "matched", blocksDoor = false),
        polygon = DOOR,
        trace =
            listOf(
                ToolCallOut(tool = "read_label", ok = true, latencyMs = 412, note = "P Shah"),
                ToolCallOut(tool = "check_door", ok = true, latencyMs = 8, note = "clear"),
                ToolCallOut(tool = "rain_outlook", ok = true, latencyMs = 220, note = "rain by 4 pm"),
                ToolCallOut(tool = "agent", ok = true, latencyMs = 3120, note = "3 tools"),
            ),
    )

internal val JO_DETAIL =
    detail(
        id = "v2",
        kind = "delivery",
        title = "Delivery",
        recipientId = "jo",
        box = BoxOut(x = 0.28f, y = 0.55f, w = 0.14f, h = 0.28f, recipientId = "jo", recipientState = "matched", blocksDoor = true),
        polygon = DOOR,
        trace =
            listOf(
                ToolCallOut(tool = "read_label", ok = true, latencyMs = 401, note = "J Lindqvist"),
                ToolCallOut(tool = "check_door", ok = true, latencyMs = 9, note = "blocking"),
                ToolCallOut(tool = "rain_outlook", ok = false, latencyMs = 0, note = "fallback: timeout"),
                ToolCallOut(tool = "agent", ok = false, latencyMs = 0, note = "fallback: timeout"),
            ),
    )

internal val VISITOR_DETAIL =
    detail(
        id = "v3",
        kind = "visitor",
        title = "Visitor",
        trace = listOf(ToolCallOut(tool = "agent", ok = true, latencyMs = 980, note = "0 tools")),
    )

@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w1920dp-h1080dp-tvdpi")
class VisitScreenshotsTest {
    @get:Rule
    val composeRule = createComposeRule()

    @OptIn(DelicateCoilApi::class)
    @Before
    fun fakeImages() {
        val engine =
            FakeImageLoaderEngine
                .Builder()
                .default(ColorDrawable(android.graphics.Color.rgb(96, 110, 128)))
                .build()
        SingletonImageLoader.setUnsafe { context ->
            ImageLoader.Builder(context).components { add(engine) }.build()
        }
    }

    private fun visit(detail: VisitDetail): @Composable () -> Unit =
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
                    VisitDetailContent(
                        detail = detail,
                        autoplayClip = false,
                        onClaim = {},
                        clipPlayer = { _, _, _ -> },
                    )
                }
            }
        }

    @Test
    fun `detail priya box outline`() {
        composeRule.setContent(visit(PRIYA_DETAIL))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/detail_priya.png")
    }

    @Test
    fun `detail jo door shaded`() {
        composeRule.setContent(visit(JO_DETAIL))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/detail_jo.png")
    }

    @Test
    fun `detail visitor no overlays`() {
        composeRule.setContent(visit(VISITOR_DETAIL))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/detail_visitor.png")
    }

    @Test
    fun `detail trace with failed step`() {
        composeRule.setContent(visit(JO_DETAIL))
        composeRule.onRoot().captureRoboImage("src/test/screenshots/detail_trace_failed.png")
    }
}
