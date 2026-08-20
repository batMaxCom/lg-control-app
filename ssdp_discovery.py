"""SSDP discovery for LG webOS TVs.

Sends multicast M-SEARCH requests over raw UDP and collects responses
from all LG webOS TVs on the local network within the timeout window.
"""

import asyncio
import logging
import select
import socket
from collections.abc import Callable
from urllib.parse import urlparse

logger = logging.getLogger("ssdp_discovery")

SSDP_IP = "239.255.255.250"
SSDP_PORT = 1900

LG_SEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    "HOST:239.255.255.250:1900\r\n"
    'MAN:"ssdp:discover"\r\n'
    "MX:3\r\n"
    "ST:urn:lge-com:service:webos-second-screen:1\r\n"
    "\r\n"
)

MSEARCH_TIMEOUT = 5


async def discover_lg_tvs(
    timeout: float = MSEARCH_TIMEOUT,
    on_found: Callable[[dict[str, str]], None] | None = None,
    cancel_event: asyncio.Event | None = None,
) -> list[dict[str, str]]:
    """Discover LG webOS TVs on the local network via SSDP.

    Returns a list of dicts with keys: ip, name, usn, location.
    If *on_found* is provided it is called for each new TV as soon as it
    is discovered, allowing the caller to update the UI incrementally.
    If *cancel_event* is provided, the search stops early when it is set.
    """
    found: dict[str, dict[str, str]] = {}

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    sock.setblocking(False)

    try:
        sock.sendto(LG_SEARCH.encode(), (SSDP_IP, SSDP_PORT))

        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            if cancel_event is not None and cancel_event.is_set():
                logger.info("SSDP search cancelled")
                break

            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break

            ready, _, _ = select.select([sock], [], [], min(remaining, 0.5))
            if not ready:
                continue

            try:
                data, addr = sock.recvfrom(2048)
            except (BlockingIOError, OSError):
                continue

            ip = addr[0]
            if ip in found:
                continue

            response = data.decode(errors="ignore")
            headers = {}
            for line in response.split("\r\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            location = headers.get("location", "")
            usn = headers.get("usn", "")
            st = headers.get("st", "")

            if not location:
                continue

            parsed = urlparse(location)
            if not parsed.hostname:
                continue

            name = usn if usn else ip
            uuid_match = usn.find("uuid:")
            if uuid_match != -1:
                uuid_str = usn[uuid_match + 5:]
                if ":" in uuid_str:
                    uuid_str = uuid_str.split(":")[0]
                name = f"LG TV ({uuid_str})"

            found[ip] = {
                "ip": ip,
                "name": name,
                "usn": usn,
                "location": location,
                "st": st,
            }
            logger.info("Found LG TV: %s at %s", name, ip)
            if on_found is not None:
                on_found(found[ip])

    except Exception as exc:
        logger.warning("SSDP search error: %s", exc)
    finally:
        sock.close()

    return list(found.values())
