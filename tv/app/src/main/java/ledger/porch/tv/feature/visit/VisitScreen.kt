package ledger.porch.tv.feature.visit

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.compose.PlayerSurface
import androidx.tv.material3.Text
import coil3.compose.AsyncImage
import ledger.porch.tv.data.dto.ToolCallOut
import ledger.porch.tv.data.dto.VisitDetail
import ledger.porch.tv.ui.components.FactChip
import ledger.porch.tv.ui.components.TvAction
import ledger.porch.tv.ui.components.sourceLabel
import ledger.porch.tv.ui.theme.TvColors
import ledger.porch.tv.ui.theme.TvSpacing
import ledger.porch.tv.ui.theme.TvType

private const val MEDIA_WEIGHT = 0.62f

private val TRACE_LABELS =
    mapOf(
        "read_label" to "Read the label",
        "check_door" to "Checked the door",
        "rain_outlook" to "Checked the rain forecast",
        "describe_clip" to "Described the clip",
        "agent" to "Agent run",
    )

@Composable
fun VisitScreen(
    viewModel: VisitViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    autoplayClip: Boolean = false,
    clipPlayer: @Composable (url: String, muted: Boolean, modifier: Modifier) -> Unit =
        { url, muted, mod -> ExoClipPlayer(url, muted, mod) },
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { viewModel.load() }
    BackHandler { onBack() }
    Column(
        modifier =
            modifier
                .fillMaxSize()
                .background(TvColors.Bg)
                .padding(
                    horizontal = TvSpacing.OverscanH,
                    vertical = TvSpacing.OverscanV,
                ),
    ) {
        when (val current = state) {
            is VisitUiState.Loading -> CenteredLine("Loading the visit…")
            is VisitUiState.Error -> {
                CenteredLine(current.message)
                TvAction(label = "Back", enabled = true, onClick = onBack)
            }
            is VisitUiState.Ready ->
                VisitDetailContent(
                    detail = current.detail,
                    autoplayClip = autoplayClip,
                    onClaim = { viewModel.claim(current.detail) },
                    clipPlayer = clipPlayer,
                )
        }
    }
}

@Composable
internal fun VisitDetailContent(
    detail: VisitDetail,
    autoplayClip: Boolean,
    onClaim: () -> Unit,
    clipPlayer: @Composable (url: String, muted: Boolean, modifier: Modifier) -> Unit,
) {
    var playing by remember { mutableStateOf(autoplayClip && detail.clipUrl != null) }
    var muted by remember { mutableStateOf(true) }
    val actionFocus = remember { FocusRequester() }
    Row(
        modifier = Modifier.fillMaxSize(),
        horizontalArrangement = Arrangement.spacedBy(TvSpacing.L),
    ) {
        Column(
            modifier = Modifier.weight(MEDIA_WEIGHT),
            verticalArrangement = Arrangement.spacedBy(TvSpacing.L),
        ) {
            MediaPanel(
                detail = detail,
                playing = playing,
                muted = muted,
                clipPlayer = clipPlayer,
                modifier = Modifier.fillMaxWidth(),
            )
            TraceSection(detail.trace)
        }
        Column(
            modifier =
                Modifier
                    .weight(1f - MEDIA_WEIGHT)
                    .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(TvSpacing.M),
        ) {
            Text(text = detail.title, style = TvType.Display, color = TvColors.Paper)
            Text(text = detail.span, style = TvType.Span, color = TvColors.Muted)
            sourceLabel(detail.provenance)?.let { label ->
                Text(text = label, style = TvType.Caption, color = TvColors.Muted)
            }
            DetailBody(
                detail,
                playing,
                muted,
                actionFocus,
                onClaim,
                onPlay = { playing = true },
                onToggleSound = { muted = !muted },
            )
        }
    }
    LaunchedEffect(Unit) { actionFocus.requestFocus() }
}

@Composable
private fun MediaPanel(
    detail: VisitDetail,
    playing: Boolean,
    muted: Boolean,
    clipPlayer: @Composable (url: String, muted: Boolean, modifier: Modifier) -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier =
            modifier
                .aspectRatio(16f / 9f)
                .clip(RoundedCornerShape(TvSpacing.S))
                .background(TvColors.Ink),
        contentAlignment = Alignment.Center,
    ) {
        if (playing && detail.clipUrl != null) {
            clipPlayer(detail.clipUrl, muted, Modifier.fillMaxSize())
        } else {
            AsyncImage(
                model = detail.heroUrl,
                contentDescription = detail.title,
                contentScale = ContentScale.Fit,
                modifier = Modifier.fillMaxSize(),
            )
            OverlayCanvas(detail)
        }
    }
}

@Composable
private fun OverlayCanvas(detail: VisitDetail) {
    Canvas(modifier = Modifier.fillMaxSize()) {
        val blockers = detail.box?.blocksDoor == true
        val polygon = detail.doorPolygon
        if (blockers && polygon != null && polygon.size >= 3) {
            val path =
                Path().apply {
                    val first = polygon.first()
                    moveTo(first[0] * size.width, first[1] * size.height)
                    for (point in polygon.drop(1)) {
                        lineTo(point[0] * size.width, point[1] * size.height)
                    }
                    close()
                }
            drawPath(path, TvColors.Terracotta.copy(alpha = 0.3f))
        }
        detail.box?.let { box ->
            drawRect(
                color = TvColors.Amber,
                topLeft = Offset(box.x * size.width, box.y * size.height),
                size = Size(box.w * size.width, box.h * size.height),
                style = Stroke(width = 2.dp.toPx()),
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DetailBody(
    detail: VisitDetail,
    playing: Boolean,
    muted: Boolean,
    actionFocus: FocusRequester,
    onClaim: () -> Unit,
    onPlay: () -> Unit,
    onToggleSound: () -> Unit,
) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(TvSpacing.S),
        verticalArrangement = Arrangement.spacedBy(TvSpacing.S),
    ) {
        detail.facts.forEach { fact -> FactChip(fact) }
    }
    Text(text = detail.description, style = TvType.Body, color = TvColors.Paper)
    DetailActions(detail, playing, muted, actionFocus, onClaim, onPlay, onToggleSound)
}

@Composable
private fun DetailActions(
    detail: VisitDetail,
    playing: Boolean,
    muted: Boolean,
    actionFocus: FocusRequester,
    onClaim: () -> Unit,
    onPlay: () -> Unit,
    onToggleSound: () -> Unit,
) {
    val claimable = detail.recipientId != null && detail.claimedBy == null
    val showPlay = detail.clipUrl != null && !playing
    Row(horizontalArrangement = Arrangement.spacedBy(TvSpacing.M)) {
        if (claimable) {
            TvAction(
                label = "It's mine",
                enabled = true,
                onClick = onClaim,
                modifier = Modifier.focusRequester(actionFocus),
            )
        }
        if (showPlay) {
            TvAction(
                label = "Play clip",
                enabled = true,
                onClick = onPlay,
                modifier = if (claimable) Modifier else Modifier.focusRequester(actionFocus),
            )
        }
        if (playing) {
            TvAction(
                label = if (muted) "Sound on" else "Mute",
                enabled = true,
                onClick = onToggleSound,
                modifier =
                    if (claimable || showPlay) {
                        Modifier
                    } else {
                        Modifier.focusRequester(actionFocus)
                    },
            )
        }
    }
}

@Composable
private fun TraceSection(trace: List<ToolCallOut>) {
    if (trace.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(TvSpacing.Xs)) {
        Text(
            text = "How this card was made",
            style = TvType.Body,
            color = TvColors.Paper,
        )
        Text(
            text = "The steps the porch clerk chose for this visit, in order.",
            style = TvType.Caption,
            color = TvColors.Muted,
        )
        trace.forEach { call -> TraceRow(call) }
    }
}

@Composable
private fun TraceRow(call: ToolCallOut) {
    val label = TRACE_LABELS[call.tool] ?: call.tool.replace('_', ' ')
    Row(horizontalArrangement = Arrangement.spacedBy(TvSpacing.S)) {
        Text(
            text = "•",
            style = TvType.Caption,
            color = if (call.ok) TvColors.Sage else TvColors.Terracotta,
        )
        Text(
            text = label,
            style = TvType.Caption,
            color = TvColors.Paper,
        )
        Text(
            text =
                if (call.ok) {
                    if (call.latencyMs == 0L) "under 1 ms" else "${call.latencyMs} ms"
                } else {
                    call.note.ifEmpty { "failed" }
                },
            style = TvType.Caption,
            color = TvColors.Muted,
        )
    }
}

@androidx.annotation.OptIn(UnstableApi::class)
@Composable
private fun ExoClipPlayer(
    url: String,
    muted: Boolean,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val player = remember { ExoPlayer.Builder(context).build() }
    DisposableEffect(player) {
        onDispose { player.release() }
    }
    LaunchedEffect(url) {
        player.setMediaItem(MediaItem.fromUri(url))
        player.prepare()
        player.play()
    }
    LaunchedEffect(muted) { player.volume = if (muted) 0f else 1f }
    PlayerSurface(player = player, modifier = modifier)
}

@Composable
private fun CenteredLine(message: String) {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(text = message, style = TvType.Body, color = TvColors.Muted)
    }
}
