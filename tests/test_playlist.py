from relayview.playlist import parse_m3u_text


def test_parses_names_groups_and_urls():
    text = '''#EXTM3U
#EXTINF:-1 tvg-name="Front fallback" group-title="Outside",Front Door
rtsp://192.168.1.2:8554/front
#EXTINF:-1 tvg-name="Garage" group-title="Outside",
rtsp://192.168.1.2:8554/garage
'''
    streams = parse_m3u_text(text)
    assert len(streams) == 2
    assert streams[0].name == "Front Door"
    assert streams[0].group == "Outside"
    assert streams[1].name == "Garage"


def test_plain_urls_get_friendly_fallback_name():
    streams = parse_m3u_text("rtsp://example.test:8554/back_garden\n")
    assert streams[0].name == "Back Garden"
