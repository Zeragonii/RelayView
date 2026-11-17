package com.relayview.android

/**
 * Health checks for live video. ExoPlayer STATE_READY is not proof that a
 * camera is actually producing pictures; only advancing video frames count.
 *
 * Times are monotonic elapsedRealtime() milliseconds, not wall-clock time.
 */
internal class StreamRecoveryPolicy(
    val firstFrameTimeoutMs: Long = 25_000L,
    val freezeTimeoutMs: Long = 20_000L,
) {
    fun shouldRecover(nowMs: Long, attemptStartedMs: Long, lastFrameMs: Long): Boolean {
        if (nowMs < attemptStartedMs) return false
        return if (lastFrameMs < attemptStartedMs) {
            nowMs - attemptStartedMs >= firstFrameTimeoutMs
        } else {
            nowMs - lastFrameMs >= freezeTimeoutMs
        }
    }

    fun retryDelayMs(consecutiveFailures: Int): Long =
        (1_000L shl consecutiveFailures.coerceIn(0, 5)).coerceAtMost(30_000L)
}
