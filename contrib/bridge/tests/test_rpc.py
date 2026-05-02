"""Regression tests for CorgiRPC.call.

Anchors the fix for the bug where corgicoind's HTTP-500-with-JSON-error-body
responses (Bitcoin-RPC convention) were raising HTTPError before the body
was parsed, defeating the bridge's per-output try/except RuntimeError handling.
"""
from unittest.mock import Mock, patch

import pytest
import requests

import bridge


def _mocked_response(status_code, json_body=None, text=""):
    resp = Mock(spec=requests.Response)
    resp.status_code = status_code
    if json_body is None:
        resp.json.side_effect = ValueError("no JSON")
        resp.text = text
    else:
        resp.json.return_value = json_body
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code}", response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


@patch("bridge.requests.post")
def test_http_500_with_json_error_raises_runtime_error(mock_post):
    """Daemon returns HTTP 500 + {"error": ...} for app-level errors like
    'scriptPubKey is not a valid bridge burn payload'. The bridge must surface
    this as RuntimeError so extract_burns can catch and skip the output."""
    mock_post.return_value = _mocked_response(
        500,
        json_body={"result": None, "error": {"code": -3, "message": "not a bridge burn"}, "id": 1},
    )
    rpc = bridge.CorgiRPC("http://test", "u", "p")
    with pytest.raises(RuntimeError, match="not a bridge burn"):
        rpc.call("decodeburn", "deadbeef")


@patch("bridge.requests.post")
def test_happy_path_returns_result(mock_post):
    mock_post.return_value = _mocked_response(
        200,
        json_body={"result": 18391, "error": None, "id": 1},
    )
    rpc = bridge.CorgiRPC("http://test", "u", "p")
    assert rpc.call("getblockcount") == 18391


@patch("bridge.requests.post")
def test_non_json_5xx_surfaces_http_error(mock_post):
    """A bare 502 from a misconfigured proxy (no JSON body) should still raise."""
    mock_post.return_value = _mocked_response(502, text="Bad Gateway")
    rpc = bridge.CorgiRPC("http://test", "u", "p")
    with pytest.raises((requests.HTTPError, RuntimeError)):
        rpc.call("getblockcount")
