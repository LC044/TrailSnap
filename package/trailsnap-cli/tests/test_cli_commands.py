import pytest
import sys
import argparse
from unittest.mock import patch

from trailsnap import cli
from trailsnap.commands import medias

pytestmark = [pytest.mark.smoke]

def test_cli_version(capsys):
    with patch.object(sys, "argv", ["trailsnap", "--version"]):
        with pytest.raises(SystemExit) as e:
            cli.main()
        assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert cli.VERSION in captured.out

def test_cli_no_args(capsys):
    with patch.object(sys, "argv", ["trailsnap"]):
        with pytest.raises(SystemExit) as e:
            cli.main()
        assert e.value.code == 2

def test_cli_help(capsys):
    with patch.object(sys, "argv", ["trailsnap", "--help"]):
        with pytest.raises(SystemExit) as e:
            cli.main()
        assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "TrailSnap CLI" in captured.out
    assert "photos" in captured.out
    assert "albums" in captured.out
    assert "tasks" in captured.out
    assert "toolbox" in captured.out


def test_thumbnail_endpoint_uses_current_owner_id():
    with patch.object(medias, "make_request", return_value={"id": "owner-1"}) as request:
        endpoint = medias._thumbnail_endpoint("photo-1", "medium")

    assert endpoint == "/medias/owner-1/photo-1/thumbnail?size=medium"
    request.assert_called_once_with("/users/me")
