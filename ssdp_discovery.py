"""SSDP discovery for LG webOS TVs.

Sends multicast M-SEARCH requests over raw UDP and collects responses
from all LG webOS TVs on the local network within the timeout window.
"""

import asyncio
import logging
import socket
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


async def discover_lg_tvs(timeout: float = MSEARCH_TIMEOUT) -> list[dict[str, str]]:
    """Discover LG webOS TVs on the local network via SSDP.

    Returns a list of dicts with keys: ip, name, usn, location.
    """
    found: dict[str, dict[str, str]] = {}
    loop = asyncio.get_running_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    sock.setblocking(False)

    try:
        sock.sendto(LG_SEARCH.encode(), (SSDP_IP, SSDP_PORT))

        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break

            try:
                data, addr = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 2048),
                    timeout=min(remaining, 0.5),
                )
            except (asyncio.TimeoutError, TimeoutError):
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

    except Exception as exc:
        logger.warning("SSDP search error: %s", exc)
    finally:
        sock.close()

    return list(found.values())
