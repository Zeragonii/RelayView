package com.relayview.android

import org.json.JSONObject

/** Same named layout payload used in Windows QSettings: {name:{rows,columns,urls}}. */
data class CameraLayout(val rows: Int, val columns: Int, val urls: List<String>) {
    fun validate(maxTiles: Int = 16): CameraLayout {
        require(rows in 1..4 && columns in 1..4 && rows * columns <= maxTiles) {
            "Android supports up to $maxTiles camera tiles"
        }
        require(urls.size <= rows * columns) { "Too many URLs for $rows×$columns layout" }
        return copy(urls = urls + List(rows * columns - urls.size) { "" })
    }
}

object Layouts {
    fun decode(json: String, maxTiles: Int = 16): Map<String, CameraLayout> {
        val root = JSONObject(json)
        val result = linkedMapOf<String, CameraLayout>()
        val names = root.keys()
        while (names.hasNext()) {
            val name = names.next()
            val raw = root.optJSONObject(name) ?: continue
            val urlsArray = raw.optJSONArray("urls") ?: continue
            val urls = (0 until urlsArray.length()).map { urlsArray.getString(it) }
            // Skip unsupported Windows profiles (up to 64 tiles), don't truncate silently.
            val layout = try {
                CameraLayout(raw.getInt("rows"), raw.getInt("columns"), urls).validate(maxTiles)
            } catch (_: Exception) { continue }
            if (name.isNotBlank()) result[name] = layout
        }
        return result
    }

    fun encode(profiles: Map<String, CameraLayout>): String = JSONObject().apply {
        for ((name, layout) in profiles) {
            put(name, JSONObject().apply {
                put("rows", layout.rows)
                put("columns", layout.columns)
                put("urls", org.json.JSONArray(layout.urls))
            })
        }
    }.toString(2)
}
