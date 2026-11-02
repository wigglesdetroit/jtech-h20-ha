"""Standalone check of the API client against the fake matrix (no HA needed)."""

import asyncio
import os
import sys

import aiohttp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "jtech_h20"))
sys.path.insert(0, os.path.dirname(__file__))

import api  # noqa: E402
from fake_matrix import start_fake  # noqa: E402


async def main() -> None:
    fake, runner, port = await start_fake()
    async with aiohttp.ClientSession() as s:
        m = api.JtechMatrix("127.0.0.1", s, port=port, settle=0.01)
        st = await m.async_get_state()
        assert st.routing == {n: 1 for n in range(1, 9)}, st.routing
        assert (
            st.edid[1].mode_name == "1080p" and st.edid[1].hdr and st.edid[1].audio_name == "5.1ch"
        )
        assert st.edid[4].mode_name == "4K60 4:2:0" and st.edid[4].three_d
        assert st.output_names[1] == "LivingR" and st.input_names[3] == "Input3"
        print("read OK:", {o: st.edid[i].mode_name for o, i in st.routing.items() if o <= 4})

        # Route kitchen (out 2) to input 3, then read back.
        await m.async_route(2, 3)
        st = await m.async_get_state()
        assert st.routing[2] == 3 and fake.routing[1] == "2"
        print("route OK: kitchen ->", st.routing[2])

        # Change only audio on input 5; everything else must be preserved.
        before = fake.edid[4]
        new = await m.async_update_edid(5, audio="2")
        assert fake.edid[4] == before[:6] + "2", (before, fake.edid[4])
        print("edid OK:", before, "->", fake.edid[4], new.audio_name)

        # Many concurrent callers: the lock must serialize them so nothing is dropped.
        await asyncio.gather(*(m.async_get_state() for _ in range(10)), m.async_route(4, 2))
        assert fake.dropped == 0, fake.dropped
        assert fake.routing[3] == "1"
        print("serialized OK: 11 concurrent calls, 0 dropped")

        # Prove the fake really does drop concurrent unserialized requests (like the real unit).
        async def raw():
            try:
                async with s.get(f"http://127.0.0.1:{port}/HDMI_MUX.js") as r:
                    return r.status
            except aiohttp.ClientError:
                return "dropped"

        res = await asyncio.gather(*(raw() for _ in range(4)))
        print("unserialized raw requests:", res)
        assert "dropped" in res

        # Safety: invalid inputs are refused before anything is sent.
        sent = len(fake.requests)
        for bad in (
            lambda: m.async_route(9, 1),
            lambda: m.async_route(1, 0),
            lambda: m.async_set_edid(1, api.Edid(mode="Z")),
        ):
            try:
                await bad()
                raise AssertionError("should have refused")
            except api.MatrixError:
                pass
        assert len(fake.requests) == sent
        print("safety OK: invalid commands refused, nothing sent")

        # Resolution logic
        st = await m.async_get_state()
        tv = {1: "4K", 2: "1080p", 3: "1080p", 4: "1080p"}
        print("resolution living:", api.resolution_for_output(st, 1, tv))
    await runner.cleanup()
    print("ALL SMOKE CHECKS PASSED")


asyncio.run(main())
