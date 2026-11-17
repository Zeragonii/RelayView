package com.relayview.android

import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Manual pull/push with visible confirmation; no silent M3U overwrites.
 */
@Composable
fun GatewaySettingsDialog(
    client: GatewayClient,
    onPull: suspend () -> Int,
    onPush: suspend () -> Unit,
    onDismiss: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf(client.url) }
    var token by remember { mutableStateOf(client.token) }
    var status by remember { mutableStateOf("Changes are local until you push them to the master playlist.") }
    var busy by remember { mutableStateOf(false) }

    fun save() {
        client.url = url
        client.token = token
    }

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("RelayView gateway") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Connect to your private PTZ gateway and shared master M3U.")
                OutlinedTextField(
                    value = url, onValueChange = { url = it },
                    label = { Text("Gateway URL (HTTPS preferred)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    singleLine = true,
                )
                OutlinedTextField(
                    value = token, onValueChange = { token = it },
                    label = { Text("API token") },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                )
                Button(enabled = !busy, onClick = {
                    save()
                    status = "Connection details saved on this device."
                }) { Text("Save connection") }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(enabled = !busy, onClick = {
                        save()
                        busy = true
                        scope.launch {
                            status = try {
                                val count = onPull()
                                "Pulled $count cameras. Local camera edits were replaced."
                            } catch (error: Exception) {
                                "Pull failed: ${error.message}"
                            }
                            busy = false
                        }
                    }) { Text("↓ Pull master") }
                    Button(enabled = !busy, onClick = {
                        save()
                        busy = true
                        scope.launch {
                            status = try {
                                onPush()
                                "Master playlist updated. Other devices can pull it."
                            } catch (error: Exception) {
                                "Push failed: ${error.message}"
                            }
                            busy = false
                        }
                    }) { Text("↑ Push local") }
                }
                Text("Pull replaces local cameras; Push replaces the master. Back up any unsynchronised changes.",
                    style = MaterialTheme.typography.bodySmall)
                Text(status, style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = { TextButton(enabled = !busy, onClick = onDismiss) { Text("Close") } },
    )
}

/**
 * Long press sends a command repeatedly so the server's 0.9 s STOP watchdog
 * extends while held. Release sends STOP. TV remote click moves briefly.
 */
@Composable
private fun PtzHoldButton(
    label: String,
    cameraId: String,
    command: String,
    client: GatewayClient,
    onError: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    Button(
        onClick = {
            scope.launch {
                try {
                    client.ptz(cameraId, command)
                    delay(250)
                    client.ptz(cameraId, "STOP")
                } catch (error: Exception) {
                    onError("PTZ: ${error.message}")
                }
            }
        },
        modifier = modifier.pointerInput(cameraId, command) {
            detectTapGestures(onPress = {
                val moving: Job = scope.launch {
                    while (isActive) {
                        try {
                            client.ptz(cameraId, command)
                        } catch (error: Exception) {
                            onError("PTZ: ${error.message}")
                        }
                        delay(250)
                    }
                }
                try {
                    tryAwaitRelease()
                } finally {
                    moving.cancel()
                    scope.launch {
                        try {
                            client.ptz(cameraId, "STOP")
                        } catch (error: Exception) {
                            onError("Stop: ${error.message}")
                        }
                    }
                }
            })
        },
    ) { Text(label) }
}

@Composable
fun PtzControlsDialog(
    camera: Camera,
    client: GatewayClient,
    onDismiss: () -> Unit,
) {
    val cameraId = camera.attrs["relayview-ptz-camera"].orEmpty()
    val scope = rememberCoroutineScope()
    var preset by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("") }
    val report: (String) -> Unit = { status = it }
    val gap = 6.dp

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Physical PTZ · ${camera.name}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Frigate camera: $cameraId")
                Text("Hold to move the camera. Digital pinch zoom/pan is separate.",
                    style = MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement = Arrangement.spacedBy(gap)) {
                    Spacer(Modifier.weight(1f))
                    PtzHoldButton("▲", cameraId, "MOVE_UP", client, report, Modifier.weight(1f))
                    Spacer(Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(gap)) {
                    PtzHoldButton("◀", cameraId, "MOVE_LEFT", client, report, Modifier.weight(1f))
                    Button(onClick = {
                        scope.launch {
                            try { client.ptz(cameraId, "STOP") }
                            catch (error: Exception) { status = error.message.orEmpty() }
                        }
                    }, modifier = Modifier.weight(1f)) { Text("STOP") }
                    PtzHoldButton("▶", cameraId, "MOVE_RIGHT", client, report, Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(gap)) {
                    Spacer(Modifier.weight(1f))
                    PtzHoldButton("▼", cameraId, "MOVE_DOWN", client, report, Modifier.weight(1f))
                    Spacer(Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(gap)) {
                    PtzHoldButton("Zoom +", cameraId, "ZOOM_IN", client, report, Modifier.weight(1f))
                    PtzHoldButton("Zoom −", cameraId, "ZOOM_OUT", client, report, Modifier.weight(1f))
                }
                OutlinedTextField(preset, { preset = it },
                    label = { Text("Preset name (optional)") }, singleLine = true)
                TextButton(onClick = {
                    scope.launch {
                        status = try {
                            client.ptz(cameraId, "preset_$preset")
                            "Preset requested."
                        } catch (error: Exception) {
                            "Preset failed: ${error.message}"
                        }
                    }
                }) { Text("Go to preset") }
                if (status.isNotBlank()) Text(status, style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = { TextButton(onClick = {
            scope.launch {
                try { client.ptz(cameraId, "STOP") }
                catch (_: Exception) { /* server watchdog remains a fail-safe */ }
            }
            onDismiss()
        }) { Text("Close") } },
    )
}
