package ledger.porch.tv.feature.today

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performKeyInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import ledger.porch.tv.data.dto.Folded
import ledger.porch.tv.data.dto.VisitCard
import ledger.porch.tv.ui.theme.PorchTheme
import ledger.porch.tv.ui.theme.TvColors
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w1920dp-h1080dp-tvdpi")
class FocusTest {
    @get:Rule
    val composeRule = createComposeRule()

    private fun key(key: Key) {
        composeRule.onRoot().performKeyInput {
            keyDown(key)
            keyUp(key)
        }
        composeRule.waitForIdle()
    }

    private fun setTodayContent(
        cards: List<VisitCard>,
        initial: String,
        onSelect: (String) -> Unit = {},
        onOpen: (String, Boolean) -> Unit = { _, _ -> },
    ) {
        composeRule.setContent {
            PorchTheme {
                Column(
                    modifier =
                        Modifier
                            .fillMaxSize()
                            .background(TvColors.Bg),
                ) {
                    TodayContent(
                        cards = cards,
                        folded = Folded(),
                        selectedId = initial,
                        offline = false,
                        onSelect = onSelect,
                        onClaim = {},
                        onOpenDetail = onOpen,
                    )
                }
            }
        }
        composeRule.waitForIdle()
    }

    @Test
    fun `hero image opens details before the actions`() {
        var opened: Pair<String, Boolean>? = null
        setTodayContent(sampleCards(), PRIYA.id, onOpen = { id, auto -> opened = id to auto })

        composeRule
            .onNodeWithContentDescription("Open details")
            .assertIsFocused()
        key(Key.DirectionCenter)
        assertEquals(PRIYA.id to false, opened)
    }

    @Test
    fun `delivery focuses image, rail moves selection, up returns to image`() {
        var selected by mutableStateOf(PRIYA.id)
        setTodayContent(sampleCards(), PRIYA.id, onSelect = { selected = it })

        composeRule
            .onNodeWithContentDescription("Open details")
            .assertIsFocused()

        key(Key.DirectionDown)
        // The image sits above the rail's left edge; the first chip gets it.
        composeRule.onNodeWithText("11:05 to 11:06 am · Delivery").assertIsFocused()
        key(Key.DirectionRight)
        key(Key.DirectionRight)
        assertEquals(VISITOR.id, selected)

        key(Key.DirectionUp)
        composeRule
            .onNodeWithContentDescription("Open details")
            .assertIsFocused()
    }
}
