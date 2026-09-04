"""Public HTML fetch with DNS pinned per connection and redirect checks.

Libraries receive HTML bytes, never a URL they could navigate again.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urljoin, urlsplit

MAX_HTML_BYTES = 2 * 1024 * 1024


def public_target(source: str):
    if not isinstance(source, str) or not 8 <= len(source) <= 4096:
        raise ValueError("source must be a bounded URL")
    if any(ord(c) <= 32 or ord(c) == 127 for c in source) or "\\" in source:
        raise ValueError("invalid URL characters")
    parsed = urlsplit(source)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("source must be HTTP(S) without embedded credentials")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("non-standard URL ports are not allowed")
    host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("local hostnames are not allowed")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("source hostname has no addresses")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global or ip.is_multicast or ip.is_reserved or (getattr(ip, "ipv4_mapped", None) and not ip.ipv4_mapped.is_global):
            raise ValueError("private or reserved source addresses are not allowed")
    return parsed, host, port, addresses


def _connection(parsed, host, port, addresses):
    family, kind, proto, _, address = addresses[0]
    sock = socket.socket(family, kind, proto)
    try:
        sock.settimeout(15)
        sock.connect(address)
        if parsed.scheme == "https":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        connection = http.client.HTTPConnection(host, port, timeout=15)
        connection.sock = sock
        return connection
    except BaseException:
        sock.close()
        raise


def fetch_html(source: str) -> tuple[str, str]:
    for _ in range(6):
        parsed, host, port, addresses = public_target(source)
        connection = _connection(parsed, host, port, addresses)
        try:
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            connection.request("GET", target, headers={"User-Agent": "StationResearch/11.12", "Accept": "text/html", "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise ValueError("redirect has no destination")
                source = urljoin(source, location)
                continue
            if response.status != 200:
                raise ValueError("source returned an unsuccessful HTTP status")
            content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise ValueError("source must return HTML or plain text")
            if response.getheader("Content-Encoding", "identity").lower() not in {"", "identity"}:
                raise ValueError("compressed responses are not accepted")
            data = response.read(MAX_HTML_BYTES + 1)
            if len(data) > MAX_HTML_BYTES:
                raise ValueError("source exceeds the 2 MiB limit")
            charset = response.headers.get_content_charset() or "utf-8"
            return data.decode(charset, errors="replace"), source
        finally:
            connection.close()
    raise ValueError("too many redirects")
