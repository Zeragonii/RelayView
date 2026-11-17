package com.relayview.android

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * RelayView Gateway HTTP API. All network work happens on Dispatchers.IO.
 * Only private app preferences store the token; URLs never contain credentials.
 */
class GatewayClient(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("relayview_gateway", Context.MODE_PRIVATE)

    var url: String
        get() = prefs.getString("url", "").orEmpty()
        set(value) { prefs.edit().putString("url", value.trim().trimEnd('/')).apply() }

    var token: String
        get() = prefs.getString("token", "").orEmpty()
        set(value) { prefs.edit().putString("token", value.trim()).apply() }

    private data class Response(val bytes: ByteArray, val etag: String)

    private fun request(method: String, path: String, data: ByteArray? = null, etag: String? = null): Response {
        val base = url
        val auth = token
        require(base.startsWith("https://", true) || base.startsWith("http://", true)) {
            "Configure an HTTP(S) gateway URL first"
        }
        require(auth.isNotBlank()) { "Configure your gateway API token first" }
        val connection = URL(base + path).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 5000
            connection.readTimeout = 5000
            connection.setRequestProperty("Authorization", "Bearer $auth")
            connection.setRequestProperty("Accept", "*/*")
            connection.instanceFollowRedirects = false
            if (etag != null) connection.setRequestProperty("If-Match", etag)
            if (data != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type",
                    if (path.contains("/ptz/")) "application/json" else "audio/x-mpegurl")
                connection.outputStream.use { it.write(data) }
            }
            val code = connection.responseCode
            if (code !in 200..299) {
                throw IOException(
                    if (code == 412) "Master changed since your update; pull and review before pushing"
                    else "Gateway returned HTTP $code"
                )
            }
            val bytes = connection.inputStream.use { it.readBytes() }
            return Response(bytes, connection.getHeaderField("ETag").orEmpty())
        } finally {
            connection.disconnect()
        }
    }

    suspend fun pullPlaylist(): String = withContext(Dispatchers.IO) {
        String(request("GET", "/api/v1/playlist").bytes, Charsets.UTF_8).removePrefix("\uFEFF")
    }

    suspend fun pushPlaylist(contents: String) = withContext(Dispatchers.IO) {
        // Conditional write protects against an intervening upload from another device.
        val etag = request("GET", "/api/v1/playlist").etag
        require(etag.isNotEmpty()) { "Gateway did not return a master playlist ETag" }
        request("PUT", "/api/v1/playlist", contents.toByteArray(Charsets.UTF_8), etag)
        Unit
    }

    suspend fun ptz(camera: String, command: String) = withContext(Dispatchers.IO) {
        require(Regex("[A-Za-z0-9_-]{1,64}").matches(camera)) { "Invalid Frigate camera ID" }
        require(command in setOf("MOVE_UP", "MOVE_DOWN", "MOVE_LEFT", "MOVE_RIGHT",
            "ZOOM_IN", "ZOOM_OUT", "STOP") ||
            Regex("preset_[A-Za-z0-9_-]{1,64}").matches(command)) {
            "Unsupported PTZ command"
        }
        request("POST", "/api/v1/ptz/$camera/command",
            """{"command":"$command"}""".toByteArray(Charsets.UTF_8))
        Unit
    }
}
