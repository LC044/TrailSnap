import json
import subprocess
import pytest
from app.utils import video_tools

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_probe_matches_display_dimensions_and_uses_container_duration(monkeypatch):
    doc = {'streams': [{'width': 1920, 'height': 1080, 'duration': 'N/A',
                        'side_data_list': [{'rotation': -90}]}], 'format': {'duration': '2.5'}}
    monkeypatch.setattr(video_tools, '_run', lambda name, args: json.dumps(doc).encode())
    assert video_tools.probe_video('portrait.mov') == (1080, 1920, 2.5)


def test_probe_does_not_return_nonfinite_duration(monkeypatch):
    doc = {'streams': [{'width': 640, 'height': 360, 'duration': 'NaN'}], 'format': {'duration': 'inf'}}
    monkeypatch.setattr(video_tools, '_run', lambda name, args: json.dumps(doc).encode())
    assert video_tools.probe_video('unknown.mkv') == (640, 360, None)


@pytest.mark.parametrize('error', [subprocess.CalledProcessError(1, 'ffmpeg'), subprocess.TimeoutExpired('ffmpeg', 15)])
def test_failed_frame_read_allows_other_thumbnail_candidates(monkeypatch, error):
    def fail(name, args):
        raise error
    monkeypatch.setattr(video_tools, '_run', fail)
    assert video_tools.extract_video_frame('broken.mp4', 0.0) is None
