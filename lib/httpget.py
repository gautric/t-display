"""Minimal HTTP/HTTPS GET.

Stock MicroPython firmware ships neither `requests` nor `urequests`, and pulling
them in with mip needs a working network already. This is the ~100 lines of
socket + ssl we actually need: one GET, optional redirect, JSON out.

Requests go out as HTTP/1.0 with Connection: close so the reply is a plain
byte stream; chunked transfer is still handled in case a CDN insists.
"""

import json
import socket
import time

import log

try:
    import ssl
except ImportError:  # older builds
    import ussl as ssl

_TAG = "http"


def _split_url(url):
    if "://" not in url:
        raise ValueError("bad url %r" % url)
    scheme, rest = url.split("://", 1)
    scheme = scheme.lower()
    hostport, _, path = rest.partition("/")
    path = "/" + path
    if ":" in hostport:
        host, port = hostport.rsplit(":", 1)
        port = int(port)
    else:
        host = hostport
        port = 443 if scheme == "https" else 80
    if scheme not in ("http", "https"):
        raise ValueError("unsupported scheme %r" % scheme)
    return scheme, host, port, path


def _wrap_tls(sock, host):
    try:
        return ssl.wrap_socket(sock, server_hostname=host)
    except AttributeError:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.verify_mode = ssl.CERT_NONE
        return ctx.wrap_socket(sock, server_hostname=host)


def _dechunk(body):
    out = bytearray()
    while body:
        line, _, body = body.partition(b"\r\n")
        try:
            size = int(line.split(b";")[0], 16)
        except ValueError:
            break
        if size == 0:
            break
        out += body[:size]
        body = body[size + 2:]
    return bytes(out)


def get(url, timeout=15, limit=32768, headers=None, redirects=2):
    """Fetch url and return the body as bytes. Raises OSError on failure."""
    scheme, host, port, path = _split_url(url)
    log.debug(_TAG, "GET %s%s", host, path)
    t0 = time.ticks_ms()
    ai = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0]
    log.debug(_TAG, "resolved %s -> %s in %d ms", host, ai[-1], log.since(t0))
    sock = socket.socket(ai[0], ai[1], ai[2])
    try:
        sock.settimeout(timeout)
        sock.connect(ai[-1])
        if scheme == "https":
            t_tls = time.ticks_ms()
            sock = _wrap_tls(sock, host)
            log.debug(_TAG, "tls handshake %d ms", log.since(t_tls))
        req = ["GET %s HTTP/1.0" % path,
               "Host: %s" % host,
               "User-Agent: micropython-t-display",
               "Accept: application/json",
               "Connection: close"]
        if headers:
            for key, value in headers.items():
                req.append("%s: %s" % (key, value))
        sock.write(("\r\n".join(req) + "\r\n\r\n").encode())

        raw = bytearray()
        while len(raw) < limit:
            chunk = sock.read(1024)
            if not chunk:
                break
            raw += chunk
    finally:
        try:
            sock.close()
        except Exception:
            pass

    head, sep, body = bytes(raw).partition(b"\r\n\r\n")
    if not sep:
        raise OSError("truncated response from %s" % host)
    lines = head.split(b"\r\n")
    parts = lines[0].split()
    if len(parts) < 2:
        raise OSError("bad status line from %s" % host)
    status = int(parts[1])

    hdrs = {}
    for line in lines[1:]:
        key, _, value = line.partition(b":")
        hdrs[key.strip().lower()] = value.strip()

    if hdrs.get(b"transfer-encoding", b"").lower() == b"chunked":
        log.debug(_TAG, "chunked reply, dechunking")
        body = _dechunk(body)

    log.debug(_TAG, "%d, %d body bytes, %d ms total", status, len(body),
              log.since(t0))

    if status in (301, 302, 303, 307, 308) and redirects > 0:
        location = hdrs.get(b"location")
        if location:
            target = location.decode()
            if target.startswith("/"):
                target = "%s://%s%s" % (scheme, host, target)
            log.debug(_TAG, "%d redirect -> %s", status, target)
            return get(target, timeout, limit, headers, redirects - 1)
    if status >= 400:
        log.warn(_TAG, "HTTP %d from %s%s", status, host, path)
        raise OSError("HTTP %d from %s%s" % (status, host, path))
    if len(raw) >= limit:
        log.warn(_TAG, "reply hit the %d byte limit, may be truncated", limit)
    return body


def get_json(url, timeout=15, limit=32768, headers=None):
    return json.loads(get(url, timeout, limit, headers))
