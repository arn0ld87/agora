"""Gzip für JSON-Antworten der API."""

from __future__ import annotations

import gzip

from flask import Response, request

MIN_GZIP_BYTES = 1024
# Stufe 1, weil der einzige gevent-Worker während des Packens blockiert.
GZIP_LEVEL = 1


def gzip_json_response(response: Response) -> Response:
    """Packt gepufferte JSON-Antworten; SSE, Streams und Dateien bleiben unberührt."""
    if (
        response.mimetype != "application/json"
        or response.direct_passthrough
        or response.is_streamed
        or "Content-Encoding" in response.headers
    ):
        return response

    response.vary.add("Accept-Encoding")
    size = response.calculate_content_length()
    if (
        request.method == "HEAD"
        or size is None
        or size < MIN_GZIP_BYTES
        or request.accept_encodings.quality("gzip") <= 0
    ):
        return response

    response.set_data(
        gzip.compress(response.get_data(), compresslevel=GZIP_LEVEL, mtime=0)
    )
    response.headers["Content-Encoding"] = "gzip"
    return response
