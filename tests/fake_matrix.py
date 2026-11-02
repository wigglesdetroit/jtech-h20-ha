"""A fake JTECH-8X8-H20 web server that answers like the real one did on 2026-11-02.

* /HDMI_MUX.js returns settingsCallback({...}) with the real unit's quirks
  (tab separators, swapped gw/sub, trailing comma).
* /@PORTn=<i>.<rand> and /@EDIDn=<7 chars>.<rand> change state.
* Like the real unit, it handles one request at a time: a request that arrives
  while another is in progress is dropped (connection closed, no answer).
"""

from __future__ import annotations

import asyncio
import re

from aiohttp import web

REAL_SNAPSHOT = {
    "edid": [
        "1100002",
        "2100002",
        "2100001",
        "3010001",
        "3010001",
        "3010001",
        "3010001",
        "3010001",
    ],
    "routing": ["0"] * 8,
    "inputs": "Input1.Input2.Input3.Input4.Input5.Input6.Input7.Input8",
    "outputs": "LivingR.Kitchen.Bathroo.Basemen.Output5.Output6.Output7.Output8",
}

_CMD_RE = re.compile(r"^@(PORT|EDID)([1-8])=([0-9A-Fa-f]+)\.")


class FakeMatrix:
    def __init__(self, drop_concurrent: bool = True, delay: float = 0.05) -> None:
        self.edid = list(REAL_SNAPSHOT["edid"])
        self.routing = list(REAL_SNAPSHOT["routing"])
        self.inputs = REAL_SNAPSHOT["inputs"]
        self.outputs = REAL_SNAPSHOT["outputs"]
        self.drop_concurrent = drop_concurrent
        self.delay = delay
        self.mac = "02:00:00:00:12:34"
        self.busy = False
        self.requests: list[str] = []
        self.dropped = 0
        self.fail_next = 0  # make the next N requests return HTTP 500
        self.app = web.Application()
        self.app.router.add_get("/{tail:.*}", self.handle)

    def status_body(self) -> str:
        parts = [
            f'"mac":"{self.mac}"',
            '"ip":"192.168.1.50"',
            '"gw":"255.255.255.0"',
            '"sub":"192.168.0.1"',
            '"MID":"8*8HDMI2.0Matrix"',
            '"DHCP":"0"',
        ]
        parts += [f'"EDID{n}Data":"{v}"' for n, v in enumerate(self.edid, 1)]
        parts += [f'"SWP{n}Data":"{v}"' for n, v in enumerate(self.routing, 1)]
        body = ",\t\t".join(parts)
        return (
            "settingsCallback({" + body + f',"MdyIPData":"{self.inputs}",'
            f'"MdyOPData":"{self.outputs}",' + "});"
        )

    async def handle(self, request: web.Request) -> web.StreamResponse:
        path = request.path_qs.lstrip("/")
        self.requests.append(path)
        if self.drop_concurrent and self.busy:
            self.dropped += 1
            request.transport.close()
            raise asyncio.CancelledError
        if self.fail_next:
            self.fail_next -= 1
            return web.Response(status=500, text="error")
        self.busy = True
        try:
            await asyncio.sleep(self.delay)
            if path == "HDMI_MUX.js":
                return web.Response(text=self.status_body(), content_type="text/html")
            m = _CMD_RE.match(path)
            if m:
                kind, n, value = m.group(1), int(m.group(2)), m.group(3).upper()
                if kind == "PORT":
                    self.routing[n - 1] = format(int(value) - 1, "X")
                else:
                    self.edid[n - 1] = value
                return web.Response(text="52=OK")
            return web.Response(status=404, text="not found")
        finally:
            self.busy = False


async def start_fake(port: int = 0, **kwargs) -> tuple[FakeMatrix, web.AppRunner, int]:
    fake = FakeMatrix(**kwargs)
    runner = web.AppRunner(fake.app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    actual = site._server.sockets[0].getsockname()[1]
    return fake, runner, actual
