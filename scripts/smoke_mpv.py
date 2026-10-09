"""Windows CI smoke test of actual pinned libmpv DLL, independent of GUI/RTSP."""
from relayview.mpv_native import MpvClient, view_properties

client = MpvClient()
client.initialize(None, headless=True)
client.property('volume', 40)
for property_name, value in view_properties(3, 0.35, 0.65).items():
    client.property(property_name, value)
assert client.read('volume') is not None
print('libmpv native API initialized and zoom/alignment properties accepted')
