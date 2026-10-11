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
                    )
                }
            }
        }
        composeRule.waitForIdle()
    }

    @Test
    fun `delivery focuses primary action, rail moves selection, up returns`() {
        var selected by mutableStateOf(PRIYA.id)
        setTodayContent(sampleCards(), PRIYA.id) { selected = it }

        composeRule.onNodeWithText("It's mine").assertIsFocused()

        key(Key.DirectionDown)
        key(Key.DirectionRight)
        key(Key.DirectionRight)
        assertEquals(VISITOR.id, selected)

        key(Key.DirectionUp)
        composeRule.onNodeWithText("It's mine").assertIsFocused()
    }

    @Test
    fun `card without actions focuses its rail chip`() {
        setTodayContent(listOf(VISITOR, STOPPED), VISITOR.id)
        composeRule
            .onNodeWithText("1:30 pm · Visitor")
            .assertIsFocused()
    }
}
