package com.relayview.android

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

private const val PREFS = "relayview_android_v1"

data class RelayState(
    val cameras: List<Camera> = emptyList(),
    val rows: Int = 2,
    val columns: Int = 2,
    val slots: List<String> = List(4) { "" },
    val selectedSlot: Int = 0,
    val profiles: Map<String, CameraLayout> = emptyMap(),
)

class RelayViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences(PREFS, 0)
    private val _state = MutableStateFlow(readState())
    val state = _state.asStateFlow()

    private fun readState(): RelayState {
        val cameras = try { M3u.parse(prefs.getString("playlist", "").orEmpty()) } catch (_: Exception) { emptyList() }
        val rows = prefs.getInt("rows", 2).coerceIn(1, 4)
        val columns = prefs.getInt("columns", 2).coerceIn(1, 4)
        val slots = prefs.getString("slots", "").orEmpty().split('\n').take(rows * columns).let {
            it + List((rows * columns - it.size).coerceAtLeast(0)) { "" }
        }
        val profiles = try { Layouts.decode(prefs.getString("profiles", "{}").orEmpty()) } catch (_: Exception) { emptyMap() }
        return RelayState(cameras, rows, columns, slots, profiles = profiles)
    }

    private fun set(next: RelayState) {
        _state.value = next
        prefs.edit()
            .putString("playlist", M3u.serialize(next.cameras))
            .putInt("rows", next.rows)
            .putInt("columns", next.columns)
            .putString("slots", next.slots.joinToString("\n"))
            .putString("profiles", Layouts.encode(next.profiles))
            .apply()
    }

    fun importPlaylist(text: String): Int {
        val cameras = M3u.parse(text).distinctBy { it.url }
        require(cameras.isNotEmpty()) { "No streams were found in the playlist" }
        val old = _state.value
        val known = cameras.map { it.url }.toSet()
        val slots = old.slots.map { if (it in known) it else "" }.toMutableList()
        if (slots.none { it.isNotEmpty() }) slots[0] = cameras[0].url
        set(old.copy(cameras = cameras, slots = slots))
        return cameras.size
    }

    fun playlistM3u(): String = M3u.serialize(_state.value.cameras)

    fun updateCamera(previousUrl: String?, camera: Camera) {
        require(camera.name.isNotBlank()) { "Camera name is required" }
        require(camera.url.startsWith("rtsp://", true) || camera.url.startsWith("rtspt://", true) ||
            camera.url.startsWith("http://", true) || camera.url.startsWith("https://", true)) {
            "Camera URLs must be RTSP, HTTP or HTTPS"
        }
        val current = _state.value
        if (current.cameras.any { it.url == camera.url && it.url != previousUrl }) {
            throw IllegalArgumentException("A camera with this URL already exists")
        }
        val cameras = current.cameras.toMutableList()
        val index = cameras.indexOfFirst { it.url == previousUrl }
        if (index >= 0) cameras[index] = camera else cameras.add(camera)
        val slots = current.slots.map { if (it == previousUrl && previousUrl != null) camera.url else it }
        set(current.copy(cameras = cameras, slots = slots))
    }

    fun removeCamera(url: String) {
        val old = _state.value
        set(old.copy(cameras = old.cameras.filterNot { it.url == url }, slots = old.slots.map { if (it == url) "" else it }))
    }

    fun toggleFavourite(url: String) {
        val old = _state.value
        set(old.copy(cameras = old.cameras.map { if (it.url == url) it.copy(favorite = !it.favorite) else it }))
    }

    fun moveCamera(url: String, delta: Int) {
        val old = _state.value
        val cameras = old.cameras.toMutableList()
        val at = cameras.indexOfFirst { it.url == url }
        if (at < 0 || at + delta !in cameras.indices) return
        java.util.Collections.swap(cameras, at, at + delta)
        set(old.copy(cameras = cameras))
    }

    fun chooseGrid(rows: Int, columns: Int) {
        CameraLayout(rows, columns, emptyList()).validate()
        val old = _state.value
        val slots = old.slots.take(rows * columns) + List((rows * columns - old.slots.size).coerceAtLeast(0)) { "" }
        set(old.copy(rows = rows, columns = columns, slots = slots, selectedSlot = old.selectedSlot.coerceAtMost(slots.lastIndex)))
    }

    fun selectSlot(index: Int) {
        if (index in _state.value.slots.indices) _state.value = _state.value.copy(selectedSlot = index)
    }

    fun assignCamera(url: String) {
        val old = _state.value
        val slots = old.slots.toMutableList()
        slots[old.selectedSlot] = url
        set(old.copy(slots = slots))
    }

    fun swapSlots(a: Int, b: Int) {
        val old = _state.value
        if (a !in old.slots.indices || b !in old.slots.indices) return
        val slots = old.slots.toMutableList()
        java.util.Collections.swap(slots, a, b)
        set(old.copy(slots = slots))
    }

    fun saveLayout(name: String) {
        require(name.isNotBlank()) { "Layout name is required" }
        val old = _state.value
        set(old.copy(profiles = old.profiles + (name.trim() to CameraLayout(old.rows, old.columns, old.slots))))
    }

    fun loadLayout(name: String) {
        val old = _state.value
        val profile = old.profiles[name]?.validate() ?: return
        set(old.copy(rows = profile.rows, columns = profile.columns, slots = profile.urls, selectedSlot = 0))
    }

    fun deleteLayout(name: String) {
        val old = _state.value
        set(old.copy(profiles = old.profiles - name))
    }

    fun importLayouts(json: String): Int {
        val loaded = Layouts.decode(json)
        require(loaded.isNotEmpty()) { "No supported layouts were found (maximum 4×4)" }
        val old = _state.value
        set(old.copy(profiles = old.profiles + loaded))
        return loaded.size
    }

    fun exportLayouts(): String = Layouts.encode(_state.value.profiles)
}
