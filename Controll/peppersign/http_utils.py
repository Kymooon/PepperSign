# -*- coding: utf-8 -*-
from __future__ import absolute_import

import json

try:
    import urllib
    import urllib2
except ImportError:
    import urllib.parse as urllib
    import urllib.request as urllib2

from peppersign.compat import PY2, text_type


def http_get_json(url, timeout=5):
    response = urllib2.urlopen(url, timeout=timeout)
    payload = response.read()
    return json.loads(payload)


def encode_multipart_formdata(files):
    boundary = "----PepperSignBoundary7MA4YWxkTrZu0gW"
    crlf = "\r\n"
    body = ""

    for field_name, filename, content_type, file_bytes in files:
        if file_bytes is None:
            file_bytes = ""
        if isinstance(file_bytes, text_type):
            file_bytes = file_bytes.encode("utf-8")
        if not PY2 and isinstance(file_bytes, bytes):
            file_bytes = file_bytes.decode("latin1")

        body += "--" + boundary + crlf
        body += 'Content-Disposition: form-data; name="%s"; filename="%s"' % (field_name, filename) + crlf
        body += "Content-Type: %s" % content_type + crlf + crlf
        body += file_bytes + crlf

    body += "--" + boundary + "--" + crlf
    content_type = "multipart/form-data; boundary=%s" % boundary
    if not PY2 and isinstance(body, str):
        body = body.encode("latin1")
    return content_type, body


def webapp_upload_audio(upload_url, session_id, wav_bytes, timeout=60):
    query_string = urllib.urlencode({"sessionId": session_id})
    url = upload_url + "?" + query_string

    content_type, body = encode_multipart_formdata([
        ("audio", "audio.wav", "application/octet-stream", wav_bytes)
    ])

    request = urllib2.Request(url, data=body)
    request.add_header("Content-Type", content_type)
    request.add_header("Content-Length", str(len(body)))

    response = urllib2.urlopen(request, timeout=timeout)
    return response.getcode(), response.read()
