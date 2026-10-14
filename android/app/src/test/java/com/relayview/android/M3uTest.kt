package com.relayview.android

import org.junit.Assert.*
import org.junit.Test

class M3uTest {
    @Test fun parsesRelayviewMetadata() {
        val content = """
            #EXTM3U
            #EXTINF:-1 group-title="Outside" relayview-favorite="1" relayview-notes="Main entrance",Front Door
            rtsp://192.168.1.50:8554/front_door
            #EXTINF:-1 group-title="Outside",Driveway
            rtsp://192.168.1.50:8554/driveway
        """.trimIndent()
        val result = M3u.parse(content)
        assertEquals(2, result.size)
        assertEquals("Front Door", result[0].name)
        assertEquals("Outside", result[0].group)
        assertTrue(result[0].favorite)
        assertEquals("Main entrance", result[0].notes)
        assertEquals("Driveway", result[1].name)
    }

    @Test fun serializerRoundTripsMetadataAndUnknownAttributes() {
        val cameras = listOf(Camera("Front Door", "rtsp://my.lan:8554/front", "Outside", true,
            "North, porch", mapOf("tvg-id" to "cam-01", "tvg-name" to "old")))
        val result = M3u.parse(M3u.serialize(cameras))
        assertEquals(cameras[0].name, result[0].name)
        assertEquals(cameras[0].url, result[0].url)
        assertTrue(result[0].favorite)
        assertEquals("North, porch", result[0].notes)
        assertEquals("cam-01", result[0].attrs["tvg-id"])
    }

    @Test fun urlNamesWorkWithoutExtendedInf() {
        val cameras = M3u.parse("#EXTM3U\nrtsp://localhost:8554/back_garden\n")
        assertEquals("back garden", cameras[0].name)
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsEmbeddedUrlNewlineOnSave() {
        M3u.serialize(listOf(Camera("Test", "rtsp://a\nmalicious")))
    }
}
