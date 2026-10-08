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

from relayview.models import Stream
from relayview.playlist import serialize_m3u


def test_relayview_metadata_and_unknown_attributes_round_trip():
    source = '''#EXTM3U
#EXTINF:-1 tvg-id="front" custom-key="keep-me" group-title="Outside" relayview-favorite="1" relayview-notes="Doorbell camera",Front Door
rtsp://example.test/front
'''
    streams = parse_m3u_text(source)
    stream = streams[0]
    assert stream.favorite is True
    assert stream.notes == "Doorbell camera"
    assert stream.attrs["custom-key"] == "keep-me"

    output = serialize_m3u(streams)
    assert 'custom-key="keep-me"' in output
    assert 'relayview-favorite="1"' in output
    assert 'relayview-notes="Doorbell camera"' in output


def test_serialization_preserves_order_and_edits():
    streams = [
        Stream(name="Garage", url="rtsp://example.test/garage", group="Outside"),
        Stream(name="Kitchen", url="rtsp://example.test/kitchen", favorite=True),
    ]
    output = serialize_m3u(streams)
    assert output.index("Garage") < output.index("Kitchen")
    assert 'group-title="Outside"' in output
    assert 'relayview-favorite="1"' in output


def test_extinf_display_name_with_commas_roundtrips():
    from relayview.playlist import serialize_m3u
    source = '#EXTM3U\n#EXTINF:-1 tvg-name="One, Two",Front, Entrance, West\nrtsp://example/cam\n'
    streams = parse_m3u_text(source)
    assert streams[0].name == "Front, Entrance, West"
    assert parse_m3u_text(serialize_m3u(streams))[0].name == streams[0].name


def test_newline_in_stream_url_is_rejected():
    import pytest
    from relayview.models import Stream
    from relayview.playlist import serialize_m3u
    with pytest.raises(ValueError):
        serialize_m3u([Stream(name="Camera", url="rtsp://example/cam\n#EXTINF:-1,Injected")])
