"""Proxy-aware IMAP4_SSL client used to read the Quotex OTP email.

Gmail sees the datacenter IP when this runs on the VPS, which can make the
OTP email slower/missing. Routing the IMAP connection through the same SOCKS
proxy as the browser (CAMOUFOX_PROXY -> QUOTEX_PROXY -> direct) makes Gmail
see the same residential IP Quotex sees.
"""

import imaplib
import logging
import os
import ssl as ssl_lib
from urllib.parse import urlparse, unquote

logger = logging.getLogger(__name__)


class _ProxyIMAP(imaplib.IMAP4_SSL):
    """IMAP4_SSL whose TCP connection is routed through a SOCKS5 proxy.

    PySocks ships no IMAP class, so we subclass and override _create_socket
    to dial imap.gmail.com:993 via the proxy (rdns=True, matching socks5h).
    """

    _proxy = None

    def __init__(self, proxy, host="imap.gmail.com", port=imaplib.IMAP4_SSL_PORT, timeout=None):
        self._proxy = proxy
        super().__init__(host, port, timeout=timeout)

    def _create_socket(self, timeout=None):
        import socks
        p = self._proxy
        s = socks.socksocket()
        s.set_proxy(
            socks.SOCKS5, p["host"], p["port"],
            username=p.get("username") or None,
            password=p.get("password") or None,
            rdns=True,
        )
        s.settimeout(timeout if timeout else 30)
        s.connect((self.host, self.port))
        ctx = ssl_lib.create_default_context()
        return ctx.wrap_socket(s, server_hostname=self.host)


def open_imap():
    """Open an IMAP4_SSL client, routed through the SOCKS proxy when set.

    Uses the same proxy precedence as the browser login
    (CAMOUFOX_PROXY -> QUOTEX_PROXY -> TELEGRAM_PROXY -> direct) so Gmail
    sees the same residential IP that Quotex sees, instead of the VPS
    datacenter IP. Falls back to a direct connection if the proxy path fails.
    """
    proxy_url = (
        os.getenv("CAMOUFOX_PROXY")
        or os.getenv("QUOTEX_PROXY")
        or os.getenv("TELEGRAM_PROXY")
    )
    if proxy_url:
        try:
            parts = urlparse(proxy_url)
            if parts.scheme.startswith("socks") and parts.hostname and parts.port:
                cfg = {
                    "host": parts.hostname,
                    "port": parts.port,
                    "username": unquote(parts.username) if parts.username else None,
                    "password": unquote(parts.password) if parts.password else None,
                }
                client = _ProxyIMAP(cfg)
                return client
            logger.info("IMAP: proxy %s not socks, using direct", parts.scheme)
        except Exception as e:
            logger.warning("IMAP: proxy connect failed (%s), falling back to direct", e)
    return imaplib.IMAP4_SSL("imap.gmail.com")
