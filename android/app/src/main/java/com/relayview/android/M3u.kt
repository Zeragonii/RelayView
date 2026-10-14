package com.relayview.android

/** Portable representation of Windows RelayView's #EXTINF metadata. */
data class Camera(
    val name: String,
    val url: String,
    val group: String = "",
    val favorite: Boolean = false,
    val notes: String = "",
    val attrs: Map<String, String> = emptyMap(),
)

object M3u {
    private val attributes = Regex("""([\w-]+)="([^"]*)"""")
    private fun truthy(value: String) = value.lowercase() in setOf("1", "true", "yes", "on", "favorite", "favourite")

    private fun extInf(line: String): Pair<String, Map<String, String>> {
        val body = line.substringAfter(':', "")
        val attrs = attributes.findAll(body).associate { it.groupValues[1] to it.groupValues[2] }
        var quote = false
        var boundary = -1
        for ((index, c) in body.withIndex()) {
            if (c == '"') quote = !quote
            if (c == ',' && !quote) { boundary = index; break }
        }
        val name = if (boundary >= 0) body.substring(boundary + 1).trim() else ""
        return (name.ifBlank { attrs["tvg-name"].orEmpty() }) to attrs
    }

    fun parse(text: String): List<Camera> {
        val result = mutableListOf<Camera>()
        var pendingName = ""
        var pendingAttrs: Map<String, String> = emptyMap()
        for (raw in text.removePrefix("\uFEFF").lineSequence()) {
            val line = raw.trim()
            if (line.isEmpty()) continue
            if (line.startsWith("#EXTINF")) {
                val (name, attrs) = extInf(line)
                pendingName = name
                pendingAttrs = attrs
                continue
            }
            if (line.startsWith('#')) continue
            // Credentials and query strings remain in the original URL, not the display name.
            val tail = line.substringBefore('?').trimEnd('/').substringAfterLast('/')
            val fallback = tail.replace('_', ' ').replace('-', ' ').trim().ifEmpty { "Stream ${result.size + 1}" }
            result += Camera(
                name = pendingName.ifEmpty { fallback }, url = line,
                group = pendingAttrs["group-title"].orEmpty(),
                favorite = truthy(pendingAttrs["relayview-favorite"].orEmpty()),
                notes = pendingAttrs["relayview-notes"].orEmpty(), attrs = pendingAttrs,
            )
            pendingName = ""
            pendingAttrs = emptyMap()
        }
        return result
    }

    fun serialize(cameras: List<Camera>): String = buildString {
        appendLine("#EXTM3U")
        for (camera in cameras) {
            require(!camera.url.contains('\r') && !camera.url.contains('\n')) { "URL contains a line break" }
            val attrs = camera.attrs.toMutableMap()
            if (camera.group.isBlank()) attrs.remove("group-title") else attrs["group-title"] = camera.group
            if ("tvg-name" in attrs) attrs["tvg-name"] = camera.name
            if (camera.favorite) attrs["relayview-favorite"] = "1" else attrs.remove("relayview-favorite")
            if (camera.notes.isNotBlank()) attrs["relayview-notes"] = camera.notes else attrs.remove("relayview-notes")
            val attrText = attrs.entries.joinToString(" ") { (key, value) ->
                "$key=\"${value.replace('"', '\'').replace('\n', ' ').replace('\r', ' ')}\""
            }
            append("#EXTINF:-1")
            if (attrText.isNotEmpty()) append(" $attrText")
            appendLine(",${camera.name.replace('\n', ' ').replace('\r', ' ')}")
            appendLine(camera.url.trim())
        }
    }
}
