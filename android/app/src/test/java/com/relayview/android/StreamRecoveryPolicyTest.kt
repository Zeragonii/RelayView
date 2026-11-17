package com.relayview.android

import org.junit.Assert.*
import org.junit.Test

class StreamRecoveryPolicyTest {
    private val policy = StreamRecoveryPolicy()

    @Test fun readyWithoutFirstFrameEventuallyTimesOut() {
        assertFalse(policy.shouldRecover(24_999L, 0L, -1L))
        assertTrue(policy.shouldRecover(25_000L, 0L, -1L))
    }

    @Test fun progressingFramesKeepStreamHealthy() {
        assertFalse(policy.shouldRecover(80_000L, 60_000L, 79_000L))
        assertFalse(policy.shouldRecover(81_000L, 60_000L, 80_000L))
    }

    @Test fun stalledLiveStreamTimesOut() {
        assertFalse(policy.shouldRecover(39_999L, 0L, 20_000L))
        assertTrue(policy.shouldRecover(40_000L, 0L, 20_000L))
    }

    @Test fun newAttemptMustProduceFreshFrames() {
        assertFalse(policy.shouldRecover(39_000L, 15_000L, 10_000L))
        assertTrue(policy.shouldRecover(40_000L, 15_000L, 10_000L))
    }

    @Test fun pausedTimeCanBeExcludedByResettingAttemptTimestamp() {
        assertFalse(policy.shouldRecover(120_000L, 115_000L, 0L))
    }

    @Test fun backoffCapsAtThirtySeconds() {
        assertEquals(1_000L, policy.retryDelayMs(0))
        assertEquals(8_000L, policy.retryDelayMs(3))
        assertEquals(30_000L, policy.retryDelayMs(5))
        assertEquals(30_000L, policy.retryDelayMs(100))
    }
}
