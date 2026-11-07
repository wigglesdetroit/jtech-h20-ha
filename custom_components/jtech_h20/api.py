"""Client for the J-Tech Digital JTECH-8X8-H20 (JTD-279) web interface.

Everything here was mapped from the matrix's own web page:

* ``GET /HDMI_MUX.js`` returns ``settingsCallback({...})`` with routing,
  EDID settings and port names for all 8 inputs/outputs. No login needed.
* ``GET /@PORT<o>=<i>.<random>`` routes output ``o`` (1-8) to input ``i`` (1-8).
* ``GET /@EDID<n>=<7 chars>.<random>`` sets input ``n``'s EDID.

The matrix also takes text commands on TCP port 5000 (the RS232 command set).
Only one is used, the routing-table command ``@T 04 <i1> <i2> ... <i8> #``: it sets
the input (0-based) for outputs 1-8 in one step. Sending the same input eight times
works like the front panel's ALL button.

EDID string, one character each:
  [0] video mode: 1=1080p 2=4K30 3=4K60 4:2:0 4=4K60 4:4:4, 5..C = copy from TV1..TV8
  [1] HDR  [2] 3D  [3] 30-bit  [4] 36-bit  [5] 48-bit   ("1" = on)
  [6] audio: 1=2.0ch 2=5.1ch 4=7.1ch

Deliberately NOT implemented: firmware upload, IP/network changes, user/password
changes, factory reset. This client cannot brick the matrix.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import re
from dataclasses import dataclass, field, replace

import aiohttp

NUM_PORTS = 8
COMMAND_PORT = 5000
# After a command-port command the web interface stops answering for about two seconds
# (measured on a real unit), so hold the queue a little longer than that.
COMMAND_SETTLE = 2.5

VIDEO_MODES: dict[str, str] = {
    "1": "1080p",
    "2": "4K30",
    "3": "4K60 4:2:0",
    "4": "4K60 4:4:4",
    **{format(4 + tv, "X"): f"Copy from TV{tv}" for tv in range(1, 9)},
}
AUDIO_MODES: dict[str, str] = {"1": "2.0ch", "2": "5.1ch", "4": "7.1ch"}
# Resolution class for each fixed video mode, used to work out what a TV gets.
MODE_RESOLUTION: dict[str, str] = {"1": "1080p", "2": "4K", "3": "4K", "4": "4K"}

_PAIR_RE = re.compile(r'"(\w+)"\s*:\s*"([^"]*)"')
_EDID_RE = re.compile(r"^[1-9A-C][01]{5}[124]$")


class MatrixError(Exception):
    """Communication with the matrix failed or it returned something unexpected."""


@dataclass(frozen=True)
class Edid:
    """EDID settings for one input."""

    mode: str = "1"
    hdr: bool = False
    three_d: bool = False
    bit30: bool = False
    bit36: bool = False
    bit48: bool = False
    audio: str = "1"

    @classmethod
    def parse(cls, raw: str) -> Edid:
        raw = raw.strip().upper()
        if not _EDID_RE.match(raw):
            raise MatrixError(f"Unexpected EDID value {raw!r}")
        return cls(
            mode=raw[0],
            hdr=raw[1] == "1",
            three_d=raw[2] == "1",
            bit30=raw[3] == "1",
            bit36=raw[4] == "1",
            bit48=raw[5] == "1",
            audio=raw[6],
        )

    def encode(self) -> str:
        flags = (self.hdr, self.three_d, self.bit30, self.bit36, self.bit48)
        out = self.mode + "".join("1" if f else "0" for f in flags) + self.audio
        if not _EDID_RE.match(out):
            raise MatrixError(f"Refusing to send invalid EDID {out!r}")
        return out

    @property
    def mode_name(self) -> str:
        return VIDEO_MODES.get(self.mode, self.mode)

    @property
    def audio_name(self) -> str:
        return AUDIO_MODES.get(self.audio, self.audio)

    @property
    def copies_tv(self) -> int | None:
        """Output number this EDID is copied from, or None for a fixed mode."""
        value = int(self.mode, 16)
        return value - 4 if value >= 5 else None


@dataclass
class MatrixState:
    """A full snapshot of the matrix."""

    routing: dict[int, int] = field(default_factory=dict)  # output -> input (1-based)
    edid: dict[int, Edid] = field(default_factory=dict)  # input -> EDID
    input_names: dict[int, str] = field(default_factory=dict)
    output_names: dict[int, str] = field(default_factory=dict)
    model: str | None = None
    mac: str | None = None

    def outputs_on_input(self, input_no: int) -> list[int]:
        return sorted(o for o, i in self.routing.items() if i == input_no)


def parse_status(text: str) -> MatrixState:
    """Parse the body of /HDMI_MUX.js. Tolerates the matrix's trailing commas."""
    values = dict(_PAIR_RE.findall(text))
    if "SWP1Data" not in values or "EDID1Data" not in values:
        raise MatrixError("Status page did not contain routing/EDID data")
    state = MatrixState(model=values.get("MID"), mac=values.get("mac"))
    for n in range(1, NUM_PORTS + 1):
        raw = values.get(f"SWP{n}Data", "").strip()
        try:
            state.routing[n] = int(raw, 16) + 1  # matrix reports 0-based
        except ValueError as err:
            raise MatrixError(f"Bad routing value {raw!r} for output {n}") from err
        state.edid[n] = Edid.parse(values.get(f"EDID{n}Data", ""))
    for key, target in (("MdyIPData", state.input_names), ("MdyOPData", state.output_names)):
        names = values.get(key, "").split(".")
        for n in range(1, NUM_PORTS + 1):
            name = names[n - 1].strip() if n - 1 < len(names) else ""
            target[n] = name or (f"Input{n}" if key == "MdyIPData" else f"Output{n}")
    return state


class JtechMatrix:
    """Async client. All requests go through one lock: the matrix handles one at a time."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        port: int = 80,
        timeout: float = 8.0,
        settle: float = 0.3,
        command_port: int = COMMAND_PORT,
    ) -> None:
        self.host = host
        self.port = port
        self.command_port = command_port
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._settle = settle
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        return f"http://{self.host}" if self.port == 80 else f"http://{self.host}:{self.port}"

    async def _get(self, path: str) -> str:
        async with self._lock:
            # The matrix sometimes drops a connection outright; one retry covers that.
            for attempt in range(2):
                try:
                    async with self._session.get(
                        self.base_url + path, timeout=self._timeout
                    ) as resp:
                        if resp.status != 200:
                            raise MatrixError(f"HTTP {resp.status} for {path}")
                        body = await resp.text(errors="replace")
                    break
                except aiohttp.ClientConnectionError as err:
                    if attempt:
                        raise MatrixError(f"Cannot reach matrix at {self.base_url}: {err}") from err
                    await asyncio.sleep(0.5)
                except (TimeoutError, aiohttp.ClientError) as err:
                    raise MatrixError(f"Cannot reach matrix at {self.base_url}: {err}") from err
            # Give the matrix a moment before the next request.
            await asyncio.sleep(self._settle)
            return body

    async def _command(self, text: str) -> str:
        """Send one text command to the command port and return whatever it answers."""
        async with self._lock:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.command_port),
                    self._timeout.total,
                )
            except (OSError, TimeoutError) as err:
                raise MatrixError(
                    f"Cannot reach matrix command port {self.host}:{self.command_port}: {err}"
                ) from err
            try:
                writer.write(text.encode("ascii"))
                await writer.drain()
                try:
                    reply = await asyncio.wait_for(reader.read(256), 1.0)
                except TimeoutError:
                    reply = b""
            except OSError as err:
                raise MatrixError(f"Command {text!r} failed: {err}") from err
            finally:
                writer.close()
                with contextlib.suppress(OSError):
                    await writer.wait_closed()
            await asyncio.sleep(max(self._settle, COMMAND_SETTLE))
            return reply.replace(b"\x00", b"").decode("ascii", errors="replace").strip()

    async def async_get_state(self) -> MatrixState:
        return parse_status(await self._get("/HDMI_MUX.js"))

    @staticmethod
    def _suffix() -> str:
        return f".{random.random()}"

    async def async_route(self, output_no: int, input_no: int) -> None:
        if not (1 <= output_no <= NUM_PORTS and 1 <= input_no <= NUM_PORTS):
            raise MatrixError(f"Invalid route output {output_no} -> input {input_no}")
        await self._get(f"/@PORT{output_no}={input_no}{self._suffix()}")

    async def async_route_all(self, input_no: int) -> str:
        """Switch every output to one input with a single command."""
        if not 1 <= input_no <= NUM_PORTS:
            raise MatrixError(f"Invalid input {input_no}")
        code = f"{input_no - 1:02d}"
        return await self._command("@T 04 " + " ".join([code] * NUM_PORTS) + " #")

    async def async_set_edid(self, input_no: int, edid: Edid) -> None:
        if not 1 <= input_no <= NUM_PORTS:
            raise MatrixError(f"Invalid input {input_no}")
        await self._get(f"/@EDID{input_no}={edid.encode()}{self._suffix()}")

    async def async_update_edid(self, input_no: int, **changes) -> Edid:
        """Read the input's current EDID fresh, change only the given fields, write it back."""
        state = await self.async_get_state()
        new = replace(state.edid[input_no], **changes)
        await self.async_set_edid(input_no, new)
        return new


def resolution_for_output(state: MatrixState, output_no: int, tv_max: dict[int, str]) -> str:
    """Best-known resolution an output receives, from its input's EDID.

    ``tv_max`` maps output -> "4K"/"1080p" (what the TV on that output supports),
    used when an input copies a TV's EDID.
    """
    edid = state.edid[state.routing[output_no]]
    copied = edid.copies_tv
    if copied is None:
        res = MODE_RESOLUTION.get(edid.mode, "unknown")
    else:
        res = tv_max.get(copied, "unknown")
    own = tv_max.get(output_no)
    if own == "1080p" and res == "4K":
        return "4K (TV may not display)"
    return res
