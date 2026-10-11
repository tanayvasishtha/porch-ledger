package ledger.porch.tv

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import ledger.porch.tv.feature.today.TodayScreen
import ledger.porch.tv.feature.today.TodayViewModel
import ledger.porch.tv.feature.visit.VisitScreen
import ledger.porch.tv.feature.visit.VisitViewModel
import ledger.porch.tv.ui.theme.PorchTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { App() }
    }
}

private sealed interface Screen {
    data object Today : Screen

    data class Detail(
        val visitId: String,
        val autoplay: Boolean,
    ) : Screen
}

@Composable
private fun App() {
    val context = LocalContext.current.applicationContext
    val graph = remember { AppGraph(context) }
    val today = remember { TodayViewModel(graph.visits) }
    var screen by remember { mutableStateOf<Screen>(Screen.Today) }
    // Set while navigating back so the rail restores focus on the same chip.
    var railFocus by remember { mutableStateOf(false) }
    PorchTheme {
        when (val current = screen) {
            is Screen.Today ->
                TodayScreen(
                    viewModel = today,
                    onOpenDetail = { id, autoplay ->
                        today.select(id)
                        railFocus = true
                        screen = Screen.Detail(id, autoplay)
                    },
                    focusRail = railFocus,
                )
            is Screen.Detail -> {
                val detail = remember(current.visitId) { VisitViewModel(graph.visits, current.visitId) }
                VisitScreen(
                    viewModel = detail,
                    autoplayClip = current.autoplay,
                    onBack = { screen = Screen.Today },
                )
            }
        }
    }
}
