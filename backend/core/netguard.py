"""Outbound connection guard (SSRF protection).

Tenants can type arbitrary IMAP/SMTP hostnames. Without a check, a malicious tenant
could make the server connect to internal services (databases, cloud metadata at
169.254.169.254, the Docker network, ...). We resolve the host and refuse private,
loopback, link-local, multicast and reserved addresses unless ALLOW_PRIVATE_HOSTS=true.
"""
import ipaddress
import socket

from django.conf import settings


class UnsafeHostError(ValueError):
    pass


def assert_public_host(host: str, port: int) -> None:
    if getattr(settings, "ALLOW_PRIVATE_HOSTS", False):
        return
    if not host or len(host) > 253:
        raise UnsafeHostError("Invalid host name.")
    if not (0 < int(port) < 65536):
        raise UnsafeHostError("Invalid port.")
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeHostError(f"Cannot resolve {host}: {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            raise UnsafeHostError(
                f"{host} resolves to a private address ({ip}); connecting to internal hosts is not allowed."
            )
