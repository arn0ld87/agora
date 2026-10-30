"""Gzip für JSON-Antworten: nur gepuffertes JSON, nie SSE oder Streams."""

from __future__ import annotations

import gzip
import inspect
import json

import pytest
from flask import Flask, Response, jsonify

from app import create_app
from app.utils.compression import MIN_GZIP_BYTES, gzip_json_response

BIG = {"text": "x" * (MIN_GZIP_BYTES * 4)}


@pytest.fixture
def client():
    app = Flask(__name__)
    app.after_request(gzip_json_response)

    @app.get("/big")
    def big():
        return jsonify(BIG)

    @app.get("/small")
    def small():
        return jsonify({"ok": True})

    @app.get("/sse")
    def sse():
        return Response(iter(["data: x\n\n"]), mimetype="text/event-stream")

    @app.get("/json-stream")
    def json_stream():
        return Response(iter(["{}"]), mimetype="application/json")

    @app.get("/encoded")
    def encoded():
        response = jsonify(BIG)
        response.headers["Content-Encoding"] = "br"
        return response

    return app.test_client()


def test_big_json_is_gzipped_and_round_trips(client):
    resp = client.get("/big", headers={"Accept-Encoding": "gzip"})

    assert resp.headers["Content-Encoding"] == "gzip"
    assert "Accept-Encoding" in resp.headers["Vary"]
    assert int(resp.headers["Content-Length"]) == len(resp.data) < MIN_GZIP_BYTES
    assert json.loads(gzip.decompress(resp.data)) == BIG


@pytest.mark.parametrize("accept", [None, "br", "gzip;q=0"])
def test_client_without_gzip_gets_plain_json(client, accept):
    headers = {"Accept-Encoding": accept} if accept else {}
    resp = client.get("/big", headers=headers)

    assert "Content-Encoding" not in resp.headers
    assert "Accept-Encoding" in resp.headers["Vary"]
    assert resp.get_json() == BIG


def test_small_json_stays_plain(client):
    resp = client.get("/small", headers={"Accept-Encoding": "gzip"})

    assert "Content-Encoding" not in resp.headers
    assert resp.get_json() == {"ok": True}


@pytest.mark.parametrize("path", ["/sse", "/json-stream"])
def test_streams_are_untouched(client, path):
    resp = client.get(path, headers={"Accept-Encoding": "gzip"})

    assert "Content-Encoding" not in resp.headers


def test_existing_encoding_is_not_gzipped_again(client):
    resp = client.get("/encoded", headers={"Accept-Encoding": "gzip"})

    assert resp.headers["Content-Encoding"] == "br"
    assert json.loads(resp.data) == BIG


def test_create_app_registers_the_hook():
    # Quelltextprüfung: create_app() hängt Guards an die Blueprint-Singletons.
    assert "app.after_request(gzip_json_response)" in inspect.getsource(create_app)
