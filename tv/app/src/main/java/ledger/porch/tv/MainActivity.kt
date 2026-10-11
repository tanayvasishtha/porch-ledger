package ledger.porch.tv

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import ledger.porch.tv.feature.today.TodayScreen
import ledger.porch.tv.feature.today.TodayViewModel
import ledger.porch.tv.ui.theme.PorchTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { App() }
    }
}

@Composable
private fun App() {
    val context = LocalContext.current.applicationContext
    val graph = remember { AppGraph(context) }
    val viewModel = remember { TodayViewModel(graph.visits) }
    PorchTheme {
        TodayScreen(viewModel)
    }
}
