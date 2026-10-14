package com.relayview.android

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** Manifest lives in GitHub Releases at releases/latest/download/android-update.json. */
data class AndroidRelease(
    val version: String,
    val code: Int,
    val packageName: String,
    val apkUrl: String,
    val sha256: String,
)

data class UpdateState(
    val busy: Boolean = false,
    val available: AndroidRelease? = null,
    val progress: Int = -1,
    val downloaded: Boolean = false,
    val message: String = "",
)

class UpdateManager(private val activity: Activity, private val repository: String) {
    private val _state = MutableStateFlow(UpdateState())
    val state = _state.asStateFlow()
    private val localApk = File(activity.cacheDir, "updates/relayview-android.apk")

    private fun request(url: String): HttpURLConnection {
        require(url.startsWith("https://")) { "Only HTTPS downloads are permitted" }
        return (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 12_000
            readTimeout = 20_000
            instanceFollowRedirects = true
            setRequestProperty("User-Agent", "RelayView-Android/${BuildConfig.VERSION_NAME}")
        }
    }

    suspend fun check(silent: Boolean = false) {
        if (repository.isBlank()) {
            if (!silent) _state.value = UpdateState(message = "Update checks are enabled in GitHub Actions builds.")
            return
        }
        _state.value = _state.value.copy(busy = true, message = if (silent) "" else "Checking GitHub Releases…")
        try {
            val release = withContext(Dispatchers.IO) {
                val connection = request("https://github.com/$repository/releases/latest/download/android-update.json")
                try {
                    check(connection.responseCode == 200) { "Update manifest unavailable (HTTP ${connection.responseCode})" }
                    val bytes = connection.inputStream.use { it.readBytes() }
                    require(bytes.size <= 100_000) { "Update manifest too large" }
                    val json = JSONObject(bytes.toString(Charsets.UTF_8))
                    AndroidRelease(
                        json.getString("version"), json.getInt("versionCode"),
                        json.getString("packageName"), json.getString("apkUrl"),
                        json.getString("sha256").lowercase(),
                    )
                } finally { connection.disconnect() }
            }
            require(release.packageName == activity.packageName) { "Update targets a different app" }
            require(release.apkUrl.startsWith("https://github.com/$repository/releases/download/")) {
                "Update file is not published by this repository"
            }
            require(Regex("[0-9a-f]{64}").matches(release.sha256)) { "Invalid update checksum" }
            val newer = release.code > BuildConfig.VERSION_CODE
            _state.value = UpdateState(
                available = if (newer) release else null,
                downloaded = newer && localApk.isFile && digest(localApk) == release.sha256,
                message = if (newer) "RelayView ${release.version} is available" else if (silent) "" else "Already up to date",
            )
        } catch (e: Exception) {
            _state.value = UpdateState(message = if (silent) "" else "Update check failed: ${e.message}")
        }
    }

    suspend fun download() {
        val release = _state.value.available ?: return
        _state.value = _state.value.copy(busy = true, progress = 0, message = "Downloading update…")
        try {
            withContext(Dispatchers.IO) {
                localApk.parentFile?.mkdirs()
                val partial = File(localApk.parentFile, "relayview-android.part.apk")
                val connection = request(release.apkUrl)
                try {
                    check(connection.responseCode == 200) { "APK download failed (HTTP ${connection.responseCode})" }
                    val length = connection.contentLengthLong
                    val digest = MessageDigest.getInstance("SHA-256")
                    var total = 0L
                    connection.inputStream.use { input ->
                        partial.outputStream().use { output ->
                            val buf = ByteArray(64 * 1024)
                            while (true) {
                                val count = input.read(buf)
                                if (count == -1) break
                                total += count
                                require(total <= 500L * 1024 * 1024) { "APK exceeds download limit" }
                                digest.update(buf, 0, count)
                                output.write(buf, 0, count)
                                if (length > 0) _state.value = _state.value.copy(progress = ((total * 100) / length).toInt().coerceIn(0, 100))
                            }
                        }
                    }
                    require(digest.digest().joinToString("") { "%02x".format(it) } == release.sha256) {
                        "APK SHA-256 verification failed"
                    }
                    @Suppress("DEPRECATION")
                    val archive = activity.packageManager.getPackageArchiveInfo(partial.absolutePath, 0)
                    require(archive?.packageName == activity.packageName) { "Downloaded APK has the wrong package ID" }
                    check(partial.renameTo(localApk)) { "Cannot move verified APK into place" }
                } finally {
                    connection.disconnect()
                    partial.delete()
                }
            }
            _state.value = _state.value.copy(busy = false, progress = 100, downloaded = true, message = "APK verified. Ready to install.")
        } catch (e: Exception) {
            _state.value = _state.value.copy(busy = false, progress = -1, downloaded = false, message = "Download failed: ${e.message}")
        }
    }

    /** User must approve Android's package installer UI; this is not silent updating. */
    fun install(): Boolean {
        if (!_state.value.downloaded || !localApk.isFile) return false
        if (Build.VERSION.SDK_INT >= 26 && !activity.packageManager.canRequestPackageInstalls()) {
            _state.value = _state.value.copy(message = "Allow RelayView to install unknown apps, then tap Install again.")
            activity.startActivity(
                Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${activity.packageName}"))
            )
            return false
        }
        val uri = FileProvider.getUriForFile(activity, "${activity.packageName}.fileprovider", localApk)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        activity.startActivity(intent)
        return true
    }

    private suspend fun digest(file: File): String = withContext(Dispatchers.IO) {
        val md = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buf = ByteArray(64 * 1024)
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                md.update(buf, 0, n)
            }
        }
        md.digest().joinToString("") { "%02x".format(it) }
    }
}
