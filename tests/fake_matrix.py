"""A fake JTECH-8X8-H20 web server that answers like the real one did on 2026-11-02.

* /HDMI_MUX.js returns settingsCallback({...}) with the real unit's quirks
  (tab separators, swapped gw/sub, trailing comma).
* /@PORTn=<i>.<rand> and /@EDIDn=<7 chars>.<rand> change state.
* A TCP command port takes ``@T <out> <in> #`` (out 00-03/11-14) and the routing
  table ``@T 04 <in1> ... <in8> #``. A short ``@T 04`` list only sets the first outputs,
  as on the real unit.
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
        self.commands: list[str] = []
        self.dropped = 0
        self.fail_next = 0  # make the next N requests return HTTP 500
        self.reset_next = 0  # drop the connection on the next N requests
        self.app = web.Application()
        self.app.router.add_get("/{tail:.*}", self.handle)
        self.app.on_cleanup.append(self._close_tcp)
        self.tcp: asyncio.Server | None = None

    async def _close_tcp(self, _app) -> None:
        if self.tcp:
            self.tcp.close()
            await self.tcp.wait_closed()

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
        if self.reset_next:
            self.reset_next -= 1
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


    async def handle_command(self, reader: asyncio.StreamReader, writer) -> None:
        data = (await reader.read(256)).decode()
        self.commands.append(data)
        table = _TABLE_RE.match(data)
        single = _TCP_RE.match(data)
        if table:
            for o, inp in enumerate(table.group(1).split()):
                self.routing[o] = format(int(inp), "X")
        elif single:
            self.routing[_OUT_CODES.index(single.group(1))] = format(int(single.group(2)), "X")
        if table or single:
            writer.write(data.encode())
            await writer.drain()
        writer.close()


_TCP_RE = re.compile(r"^@T (0[0-3]|1[1-4]) (0[0-7]) #$")
_TABLE_RE = re.compile(r"^@T 04((?: 0[0-7]){1,8}) #$")
_OUT_CODES = ["00", "01", "02", "03", "11", "12", "13", "14"]


async def start_fake(port: int = 0, **kwargs) -> tuple[FakeMatrix, web.AppRunner, int]:
    fake = FakeMatrix(**kwargs)
    runner = web.AppRunner(fake.app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    actual = site._server.sockets[0].getsockname()[1]
    fake.tcp = await asyncio.start_server(fake.handle_command, "127.0.0.1", 0)
    fake.command_port = fake.tcp.sockets[0].getsockname()[1]
    return fake, runner, actual
