package com.relayview.android

import android.os.Bundle
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.focusable
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.rtsp.RtspMediaSource
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private val background = Color(0xFF10151D)
private val pane = Color(0xFF192230)
private val panel = Color(0xFF243145)
private val accent = Color(0xFF5EACEB)

class MainActivity : ComponentActivity() {
    private val model: RelayViewModel by viewModels()
    private val updates by lazy { UpdateManager(this, BuildConfig.UPDATE_REPO) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Android 15+ enforces edge-to-edge for targetSdk 35. Use the same
        // window behaviour on older devices, then handle safe drawing insets
        // explicitly in Compose instead of relying on OEM-specific defaults.
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = accent, surface = pane, background = background)) {
                val state by model.state.collectAsState()
                val update by updates.state.collectAsState()
                val scope = rememberCoroutineScope()
                val context = LocalContext.current
                var editCamera by remember { mutableStateOf<Camera?>(null) }
                var cameraDialog by remember { mutableStateOf(false) }
                var showLayouts by remember { mutableStateOf(false) }
                var showUpdates by remember { mutableStateOf(false) }
                // These are small UI preferences, not persisted playlist data.
                // Save them across Activity recreation (including orientation changes).
                var fullscreen by rememberSaveable { mutableStateOf<Int?>(null) }
                var showList by rememberSaveable { mutableStateOf(true) }
                var muted by rememberSaveable { mutableStateOf(true) }
                var paused by rememberSaveable { mutableStateOf(false) }
                var cameraFilter by rememberSaveable { mutableStateOf("") }
                var favouritesOnly by rememberSaveable { mutableStateOf(false) }

                // Fullscreen means immersive video, not merely a 1x1 grid.
                // Restore system bars on exit and when this Activity is disposed.
                DisposableEffect(fullscreen) {
                    val controller = WindowCompat.getInsetsController(window, window.decorView)
                    if (fullscreen != null) {
                        controller.systemBarsBehavior =
                            WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                        controller.hide(WindowInsetsCompat.Type.systemBars())
                    } else {
                        controller.show(WindowInsetsCompat.Type.systemBars())
                    }
                    onDispose { controller.show(WindowInsetsCompat.Type.systemBars()) }
                }
                BackHandler(enabled = fullscreen != null) { fullscreen = null }

                fun notify(message: String) { Toast.makeText(context, message, Toast.LENGTH_LONG).show() }
                val importPlaylist = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
                    if (uri != null) runCatching {
                        val contents = contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
                            ?: error("Cannot read playlist")
                        val count = model.importPlaylist(contents)
                        notify("Imported $count cameras")
                        showList = true
                    }.onFailure { notify("Import failed: ${it.message}") }
                }
                val exportPlaylist = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("audio/x-mpegurl")) { uri ->
                    if (uri != null) runCatching {
                        contentResolver.openOutputStream(uri)?.bufferedWriter()?.use { it.write(model.playlistM3u()) }
                            ?: error("Cannot write playlist")
                        notify("Playlist exported")
                    }.onFailure { notify("Export failed: ${it.message}") }
                }
                val importLayouts = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
                    if (uri != null) runCatching {
                        val data = contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
                            ?: error("Cannot read layouts")
                        notify("Imported ${model.importLayouts(data)} layouts")
                    }.onFailure { notify("Layout import failed: ${it.message}") }
                }
                val exportLayouts = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
                    if (uri != null) runCatching {
                        contentResolver.openOutputStream(uri)?.bufferedWriter()?.use { it.write(model.exportLayouts()) }
                            ?: error("Cannot write layouts")
                        notify("Layouts exported")
                    }.onFailure { notify("Layout export failed: ${it.message}") }
                }

                LaunchedEffect(Unit) { updates.check(silent = true) }

                RelayScreen(
                    state = state, muted = muted, paused = paused, fullscreen = fullscreen,
                    showList = showList, onToggleList = { showList = !showList },
                    cameraFilter = cameraFilter, onCameraFilter = { cameraFilter = it },
                    favouritesOnly = favouritesOnly, onFavouritesOnly = { favouritesOnly = it },
                    onSelect = model::selectSlot, onAssign = model::assignCamera,
                    onGrid = model::chooseGrid, onSwap = model::swapSlots,
                    onFullscreen = { fullscreen = it }, onMute = { muted = !muted }, onPause = { paused = !paused },
                    onImport = { importPlaylist.launch(arrayOf("*/*")) },
                    onExport = { exportPlaylist.launch("RelayView.m3u") },
                    onAdd = { editCamera = null; cameraDialog = true },
                    onEdit = { editCamera = it; cameraDialog = true },
                    onFavourite = model::toggleFavourite, onMoveCamera = model::moveCamera,
                    onLayouts = { showLayouts = true },
                    onUpdates = { showUpdates = true },
                    updateAvailable = update.available != null,
                )

                if (cameraDialog) CameraEditDialog(
                    camera = editCamera,
                    onDismiss = { cameraDialog = false },
                    onSave = { camera ->
                        runCatching { model.updateCamera(editCamera?.url, camera) }
                            .onSuccess { cameraDialog = false }
                            .onFailure { notify(it.message.orEmpty()) }
                    },
                    onRemove = editCamera?.let { current ->
                        { model.removeCamera(current.url); cameraDialog = false }
                    },
                )
                if (showLayouts) LayoutDialog(
                    profiles = state.profiles.keys.sorted(),
                    onDismiss = { showLayouts = false },
                    onSave = { name -> runCatching { model.saveLayout(name) }.onFailure { notify(it.message.orEmpty()) } },
                    onLoad = { name -> model.loadLayout(name); showLayouts = false },
                    onDelete = model::deleteLayout,
                    onImport = { importLayouts.launch(arrayOf("application/json", "*/*")) },
                    onExport = { exportLayouts.launch("RelayView-layouts.json") },
                )
                if (showUpdates) UpdateDialog(
                    state = update,
                    onDismiss = { showUpdates = false },
                    onCheck = { scope.launch { updates.check() } },
                    onDownload = { scope.launch { updates.download() } },
                    onInstall = { runCatching { updates.install() }.onFailure { notify(it.message.orEmpty()) } },
                )
            }
        }
    }
}

@Composable
private fun RelayScreen(
    state: RelayState, muted: Boolean, paused: Boolean, fullscreen: Int?, showList: Boolean,
    cameraFilter: String, onCameraFilter: (String) -> Unit,
    favouritesOnly: Boolean, onFavouritesOnly: (Boolean) -> Unit,
    onToggleList: () -> Unit, onSelect: (Int) -> Unit, onAssign: (String) -> Unit,
    onGrid: (Int, Int) -> Unit, onSwap: (Int, Int) -> Unit,
    onFullscreen: (Int?) -> Unit, onMute: () -> Unit, onPause: () -> Unit,
    onImport: () -> Unit, onExport: () -> Unit, onAdd: () -> Unit, onEdit: (Camera) -> Unit,
    onFavourite: (String) -> Unit, onMoveCamera: (String, Int) -> Unit,
    onLayouts: () -> Unit, onUpdates: () -> Unit, updateAvailable: Boolean,
) {
    var gridMenu by remember { mutableStateOf(false) }
    Scaffold(
        modifier = Modifier
            .fillMaxSize()
            .background(background)
            // The normal camera UI must avoid status/navigation bars and cutouts,
            // including landscape side insets. Immersive fullscreen intentionally
            // fills the display, with system bars hidden by MainActivity.
            .then(if (fullscreen == null) Modifier.safeDrawingPadding() else Modifier),
        // Insets are applied once to the whole normal screen, including our
        // custom toolbar. Scaffold's default insets must not pad it a second time.
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        containerColor = background,
        topBar = {
            if (fullscreen == null) Surface(color = pane) {
                Row(Modifier.fillMaxWidth().height(58.dp).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onToggleList) { Icon(Icons.Default.Menu, "Camera list") }
                    Text("RelayView", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f), maxLines = 1)
                    Box {
                        TextButton(onClick = { gridMenu = true }) { Text("${state.rows}×${state.columns}") }
                        DropdownMenu(expanded = gridMenu, onDismissRequest = { gridMenu = false }) {
                            listOf(1 to 1, 1 to 2, 2 to 2, 3 to 3, 4 to 4).forEach { (r, c) ->
                                DropdownMenuItem(text = { Text("${r}×${c}") }, onClick = { onGrid(r, c); onFullscreen(null); gridMenu = false })
                            }
                        }
                    }
                    IconButton(onClick = onMute) { Icon(if (muted) Icons.Default.VolumeOff else Icons.Default.VolumeUp, "Mute all") }
                    IconButton(onClick = onPause) { Icon(if (paused) Icons.Default.PlayArrow else Icons.Default.Pause, "Pause all") }
                    IconButton(onClick = onLayouts) { Icon(Icons.Default.GridView, "Saved layouts") }
                    BadgedBox(badge = { if (updateAvailable) Badge() }) {
                        IconButton(onClick = onUpdates) { Icon(Icons.Default.SystemUpdate, "Updates") }
                    }
                }
            }
        },
    ) { innerPadding ->
        BoxWithConstraints(Modifier.fillMaxSize().padding(innerPadding)) {
            val wide = maxWidth >= 700.dp
            if (fullscreen != null) {
                // Completely hide the camera list and app toolbar in immersive mode.
                GridViewer(Modifier.fillMaxSize(), state, fullscreen, muted, paused,
                    onSelect, onFullscreen, onSwap)
            } else if (wide) {
                Row(Modifier.fillMaxSize()) {
                    if (showList) CameraSidebar(
                        Modifier.width(300.dp).fillMaxHeight(), state, onAssign,
                        cameraFilter, onCameraFilter, favouritesOnly, onFavouritesOnly,
                        onImport, onExport, onAdd, onEdit, onFavourite, onMoveCamera,
                    )
                    GridViewer(Modifier.weight(1f).fillMaxHeight(), state, fullscreen, muted, paused,
                        onSelect, onFullscreen, onSwap)
                }
            } else {
                Column(Modifier.fillMaxSize()) {
                    if (showList) CameraSidebar(
                        Modifier.fillMaxWidth().weight(0.48f), state, onAssign,
                        cameraFilter, onCameraFilter, favouritesOnly, onFavouritesOnly,
                        onImport, onExport, onAdd, onEdit, onFavourite, onMoveCamera,
                    )
                    GridViewer(Modifier.fillMaxWidth().weight(if (showList) 0.52f else 1f), state,
                        fullscreen, muted, paused, onSelect, onFullscreen, onSwap)
                }
            }
        }
    }
}

@Composable
private fun CameraSidebar(
    modifier: Modifier, state: RelayState, onAssign: (String) -> Unit,
    filter: String, onFilterChange: (String) -> Unit,
    favouritesOnly: Boolean, onFavouritesOnly: (Boolean) -> Unit,
    onImport: () -> Unit, onExport: () -> Unit, onAdd: () -> Unit, onEdit: (Camera) -> Unit,
    onFavourite: (String) -> Unit, onMove: (String, Int) -> Unit,
) {
    Column(modifier.background(pane).padding(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Cameras", fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            IconButton(onClick = onImport) { Icon(Icons.Default.FolderOpen, "Import M3U") }
            IconButton(onClick = onExport) { Icon(Icons.Default.SaveAlt, "Export M3U") }
            IconButton(onClick = onAdd) { Icon(Icons.Default.AddCircle, "Add camera") }
        }
        OutlinedTextField(
            value = filter, onValueChange = onFilterChange,
            label = { Text("Search cameras") }, singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = favouritesOnly, onCheckedChange = onFavouritesOnly)
            Text("Favourites only", style = MaterialTheme.typography.labelMedium)
            Spacer(Modifier.weight(1f))
            Text("Tile ${state.selectedSlot + 1}", color = accent, style = MaterialTheme.typography.labelMedium)
        }
        val visible = state.cameras.filter { camera ->
            (!favouritesOnly || camera.favorite) && (camera.name.contains(filter, true) || camera.group.contains(filter, true))
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(3.dp)) {
            items(visible, key = { it.url }) { camera ->
                Surface(color = if (state.slots.getOrNull(state.selectedSlot) == camera.url) panel else background,
                    shape = RoundedCornerShape(6.dp)) {
                    Row(Modifier.fillMaxWidth().clickable { onAssign(camera.url) }.padding(horizontal = 8.dp, vertical = 5.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(camera.name, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Medium)
                            if (camera.group.isNotBlank()) Text(camera.group, color = Color.LightGray, style = MaterialTheme.typography.labelSmall)
                        }
                        IconButton(onClick = { onFavourite(camera.url) }, modifier = Modifier.size(40.dp)) {
                            Icon(if (camera.favorite) Icons.Default.Star else Icons.Default.StarBorder, "Favourite",
                                tint = if (camera.favorite) Color(0xFFFFCD5C) else Color.Gray)
                        }
                        var menu by remember { mutableStateOf(false) }
                        Box {
                            IconButton(onClick = { menu = true }, modifier = Modifier.size(40.dp)) {
                                Icon(Icons.Default.MoreVert, "Camera options")
                            }
                            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                                DropdownMenuItem(text = { Text("Edit") }, onClick = { menu = false; onEdit(camera) })
                                DropdownMenuItem(text = { Text("Move up") }, onClick = { menu = false; onMove(camera.url, -1) })
                                DropdownMenuItem(text = { Text("Move down") }, onClick = { menu = false; onMove(camera.url, 1) })
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun GridViewer(
    modifier: Modifier, state: RelayState, fullscreen: Int?, muted: Boolean, paused: Boolean,
    onSelect: (Int) -> Unit, onFullscreen: (Int?) -> Unit, onSwap: (Int, Int) -> Unit,
) {
    val indexByUrl = state.cameras.associateBy { it.url }
    var swapSource by rememberSaveable { mutableStateOf<Int?>(null) }
    Box(modifier.background(background).padding(if (fullscreen == null) 4.dp else 0.dp)) {
        Column(Modifier.fillMaxSize()) {
            if (fullscreen == null) {
                Row(Modifier.fillMaxWidth().height(34.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("LIVE GRID", color = accent, style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.weight(1f))
                    if (swapSource != null) Text("Swap: select another tile", color = accent,
                        style = MaterialTheme.typography.labelSmall)
                }
            }
            val rows = if (fullscreen == null) state.rows else 1
            val columns = if (fullscreen == null) state.columns else 1
            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                repeat(rows) { row ->
                    Row(Modifier.weight(1f).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        repeat(columns) { column ->
                            val index = fullscreen ?: row * columns + column
                            val camera = indexByUrl[state.slots.getOrNull(index)]
                            key(index, camera?.url) {
                                CameraTile(
                                    modifier = Modifier.weight(1f).fillMaxHeight(), camera = camera,
                                    index = index, selected = index == state.selectedSlot,
                                    muted = muted, paused = paused,
                                    preferSubstream = fullscreen == null && state.rows * state.columns > 1,
                                    compact = fullscreen == null && state.rows * state.columns > 1,
                                    isFullscreen = fullscreen != null,
                                    onSelect = {
                                        if (swapSource != null && swapSource != index) {
                                            onSwap(swapSource!!, index); swapSource = null
                                        } else onSelect(index)
                                    },
                                    onFullscreen = { onFullscreen(if (fullscreen == index) null else index) },
                                    onSwap = { swapSource = if (swapSource == index) null else index },
                                )
                            }
                        }
                    }
                }
            }
        }
        if (fullscreen != null) {
            // Always-visible escape hatch for touch devices and Android TV remotes.
            FilledTonalIconButton(
                onClick = { onFullscreen(null) },
                modifier = Modifier.align(Alignment.TopEnd).padding(8.dp),
            ) { Icon(Icons.Default.FullscreenExit, contentDescription = "Exit fullscreen") }
        }
    }
}

@OptIn(UnstableApi::class)
@Composable
private fun CameraTile(
    modifier: Modifier, camera: Camera?, index: Int, selected: Boolean, muted: Boolean, paused: Boolean,
    preferSubstream: Boolean, compact: Boolean, isFullscreen: Boolean,
    onSelect: () -> Unit, onFullscreen: () -> Unit, onSwap: () -> Unit,
) {
    val low = camera?.attrs?.get("relayview-substream").orEmpty()
    val streamUrl = if (preferSubstream && (low.startsWith("rtsp://", true) ||
        low.startsWith("http://", true) || low.startsWith("https://", true))) low else camera?.url
    var zoom by rememberSaveable(streamUrl) { mutableFloatStateOf(1f) }
    var offset by remember(streamUrl) { mutableStateOf(Offset.Zero) }
    var status by remember(streamUrl) { mutableStateOf("No camera") }
    var retries by remember(streamUrl) { mutableIntStateOf(0) }
    var hasFocus by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val scope = rememberCoroutineScope()
    val currentPaused by rememberUpdatedState(paused)
    val player = remember(streamUrl) {
        streamUrl?.let { url ->
            ExoPlayer.Builder(context).build().apply {
                val item = MediaItem.fromUri(url)
                if (url.startsWith("rtsp", true)) {
                    setMediaSource(RtspMediaSource.Factory().setForceUseRtpTcp(true).setTimeoutMs(10000).createMediaSource(item))
                } else {
                    setMediaItem(item) // ExoPlayer's default factory handles HTTP progressive and HLS.
                }
                playWhenReady = !paused
                prepare()
            }
        }
    }
    LaunchedEffect(player, paused, muted) {
        player?.let { it.volume = if (muted) 0f else 1f; it.playWhenReady = !paused }
    }
    DisposableEffect(player, lifecycle) {
        var pendingRetry: Job? = null
        var bufferStart = 0L
        fun recover() {
            if (player == null || pendingRetry?.isActive == true) return
            status = "Reconnecting…"
            pendingRetry = scope.launch {
                delay((1_000L shl retries.coerceAtMost(5)).coerceAtMost(30_000L))
                retries++
                player.seekToDefaultPosition()
                player.prepare()
                player.playWhenReady = !currentPaused
            }
        }
        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                when (playbackState) {
                    Player.STATE_READY -> { status = ""; retries = 0; bufferStart = 0L; pendingRetry?.cancel() }
                    Player.STATE_BUFFERING -> { status = "Buffering…"; if (bufferStart == 0L) bufferStart = android.os.SystemClock.elapsedRealtime() }
                    Player.STATE_ENDED -> recover()
                }
            }
            override fun onPlayerError(error: PlaybackException) {
                // Never render RTSP URLs; they may contain passwords.
                status = "Stream error · retrying"
                recover()
            }
        }
        player?.addListener(listener)
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) player?.pause()
            if (event == Lifecycle.Event.ON_START && !currentPaused) player?.play()
        }
        lifecycle.addObserver(observer)
        val watchdog = scope.launch {
            while (true) {
                delay(5000)
                if (player?.playbackState == Player.STATE_BUFFERING && bufferStart != 0L &&
                    android.os.SystemClock.elapsedRealtime() - bufferStart > 20_000) {
                    bufferStart = 0L
                    recover()
                }
            }
        }
        onDispose {
            lifecycle.removeObserver(observer)
            watchdog.cancel()
            pendingRetry?.cancel()
            player?.removeListener(listener)
            player?.release()
        }
    }
    val shape = RoundedCornerShape(7.dp)
    Box(modifier.clip(shape).background(Color.Black).border(if (selected || hasFocus) 2.dp else 1.dp,
        if (selected || hasFocus) accent else panel, shape)) {
        if (player != null) {
            AndroidView(
                factory = { ctx ->
                    (android.view.LayoutInflater.from(ctx).inflate(R.layout.video_player, null) as PlayerView).apply {
                        this.player = player
                        setKeepContentOnPlayerReset(true)
                    }
                },
                update = { it.player = player },
                modifier = Modifier.fillMaxSize().graphicsLayer {
                    scaleX = zoom; scaleY = zoom
                    translationX = offset.x; translationY = offset.y
                },
            )
        }
        Box(Modifier.fillMaxSize()
            .pointerInput(streamUrl) {
                detectTransformGestures { _, pan, change, _ ->
                    zoom = (zoom * change).coerceIn(1f, 5f)
                    if (zoom == 1f) offset = Offset.Zero
                    else {
                        val xLimit = size.width * (zoom - 1f) / 2f
                        val yLimit = size.height * (zoom - 1f) / 2f
                        offset = Offset((offset.x + pan.x).coerceIn(-xLimit, xLimit),
                            (offset.y + pan.y).coerceIn(-yLimit, yLimit))
                    }
                }
            }
            .pointerInput(index) { detectTapGestures(onTap = { onSelect() }, onDoubleTap = { onFullscreen() }) }
            .onFocusChanged { hasFocus = it.isFocused }
            .onKeyEvent { event ->
                if (event.type == KeyEventType.KeyUp &&
                    (event.key == Key.Enter || event.key == Key.DirectionCenter || event.key == Key.NumPadEnter)) {
                    onSelect()
                    true
                } else false
            }
            .focusable()
        )
        Row(Modifier.align(Alignment.TopStart).fillMaxWidth().background(Color(0xAA10151D)).padding(horizontal = 6.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Text("${index + 1} · ${camera?.name ?: "Empty"}", fontWeight = FontWeight.SemiBold,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
                style = MaterialTheme.typography.labelSmall, modifier = Modifier.weight(1f))
            if (status.isNotEmpty()) Text(status, color = Color.LightGray, style = MaterialTheme.typography.labelSmall)
        }
        Row(Modifier.align(Alignment.BottomEnd).background(Color(0xCC10151D)), verticalAlignment = Alignment.CenterVertically) {
            SmallIcon(Icons.Default.SwapHoriz, "Swap tile", onSwap)
            if (!compact) {
                SmallIcon(Icons.Default.Remove, "Zoom out", { zoom = (zoom - .25f).coerceAtLeast(1f); if (zoom == 1f) offset = Offset.Zero })
                Text("${(zoom * 100).toInt()}%", style = MaterialTheme.typography.labelSmall)
                SmallIcon(Icons.Default.Add, "Zoom in", { zoom = (zoom + .25f).coerceAtMost(5f) })
            }
            if (zoom > 1f && !compact) {
                SmallIcon(Icons.Default.KeyboardArrowLeft, "Pan left", { offset += Offset(32f, 0f) })
                SmallIcon(Icons.Default.KeyboardArrowRight, "Pan right", { offset += Offset(-32f, 0f) })
                SmallIcon(Icons.Default.KeyboardArrowUp, "Pan up", { offset += Offset(0f, 32f) })
                SmallIcon(Icons.Default.KeyboardArrowDown, "Pan down", { offset += Offset(0f, -32f) })
            }
            SmallIcon(if (isFullscreen) Icons.Default.FullscreenExit else Icons.Default.Fullscreen,
                if (isFullscreen) "Exit fullscreen" else "Fullscreen", onFullscreen)
        }
    }
}

@Composable
private fun SmallIcon(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, onClick: () -> Unit) {
    IconButton(onClick = onClick, modifier = Modifier.size(32.dp)) { Icon(icon, label, modifier = Modifier.size(17.dp)) }
}

@Composable
private fun CameraEditDialog(camera: Camera?, onDismiss: () -> Unit, onSave: (Camera) -> Unit, onRemove: (() -> Unit)?) {
    var name by remember(camera) { mutableStateOf(camera?.name.orEmpty()) }
    var url by remember(camera) { mutableStateOf(camera?.url.orEmpty()) }
    var group by remember(camera) { mutableStateOf(camera?.group.orEmpty()) }
    var notes by remember(camera) { mutableStateOf(camera?.notes.orEmpty()) }
    var substream by remember(camera) { mutableStateOf(camera?.attrs?.get("relayview-substream").orEmpty()) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(if (camera == null) "Add camera" else "Edit camera") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(name, { name = it }, label = { Text("Camera name") }, singleLine = true)
                OutlinedTextField(url, { url = it }, label = { Text("RTSP / HLS / HTTP URL") }, minLines = 2,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
                OutlinedTextField(group, { group = it }, label = { Text("Group") }, singleLine = true)
                OutlinedTextField(notes, { notes = it }, label = { Text("Notes") }, minLines = 2)
                OutlinedTextField(substream, { substream = it },
                    label = { Text("Optional H.264 grid substream URL") }, minLines = 2)
                if (onRemove != null) TextButton(onClick = onRemove) { Text("Delete camera", color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = { TextButton(onClick = {
            val attrs = (camera?.attrs ?: emptyMap()).toMutableMap()
            if (substream.isBlank()) attrs.remove("relayview-substream")
            else attrs["relayview-substream"] = substream.trim()
            onSave(Camera(name.trim(), url.trim(), group.trim(), camera?.favorite ?: false, notes.trim(), attrs))
        }) { Text("Save") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun LayoutDialog(profiles: List<String>, onDismiss: () -> Unit, onSave: (String) -> Unit,
    onLoad: (String) -> Unit, onDelete: (String) -> Unit, onImport: () -> Unit, onExport: () -> Unit) {
    var name by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Saved camera layouts") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedTextField(name, { name = it }, label = { Text("New layout name") }, singleLine = true)
                TextButton(enabled = name.isNotBlank(), onClick = { onSave(name); name = "" }) { Text("Save current grid") }
                HorizontalDivider()
                Column(Modifier.heightIn(max = 260.dp).verticalScroll(rememberScrollState())) {
                    for (profile in profiles) Row(verticalAlignment = Alignment.CenterVertically) {
                        TextButton(modifier = Modifier.weight(1f), onClick = { onLoad(profile) }) { Text(profile) }
                        IconButton(onClick = { onDelete(profile) }) { Icon(Icons.Default.Delete, "Delete $profile") }
                    }
                }
                HorizontalDivider()
                Row {
                    TextButton(onClick = onImport) { Text("Import JSON") }
                    TextButton(onClick = onExport) { Text("Export JSON") }
                }
            }
        }, confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } },
    )
}

@Composable
private fun UpdateDialog(state: UpdateState, onDismiss: () -> Unit, onCheck: () -> Unit,
    onDownload: () -> Unit, onInstall: () -> Unit) {
    AlertDialog(onDismissRequest = onDismiss, title = { Text("RelayView Android updates") }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Installed: ${BuildConfig.VERSION_NAME}")
            Text(state.message.ifBlank { "Check GitHub Releases for updates." })
            if (state.busy && state.progress < 0) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (state.busy && state.progress >= 0) LinearProgressIndicator(progress = { state.progress / 100f }, modifier = Modifier.fillMaxWidth())
            state.available?.let { Text("Available version: ${it.version}") }
            Text("Android will ask you to approve the APK installation.", style = MaterialTheme.typography.bodySmall, color = Color.LightGray)
        }
    }, confirmButton = {
        Row {
            TextButton(onClick = onCheck, enabled = !state.busy) { Text("Check") }
            if (state.available != null && !state.downloaded)
                TextButton(onClick = onDownload, enabled = !state.busy) { Text("Download") }
            if (state.downloaded)
                TextButton(onClick = onInstall, enabled = !state.busy) { Text("Install") }
        }
    }, dismissButton = { TextButton(onClick = onDismiss) { Text("Close") } })
}
