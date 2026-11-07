"""End-to-end tests: real Home Assistant + the integration + the fake matrix over HTTP."""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jtech_h20.const import CONF_COMMAND_PORT, DOMAIN
from tests.fake_matrix import start_fake

pytestmark = pytest.mark.enable_socket

NAMES = {
    "input_1": "Roku Ultra",
    "input_2": "Onn 4K Pro",
    "input_3": "Bathroom Roku",
    "input_4": "Camera Wall",
    **{f"input_{n}": "" for n in range(5, 9)},
    "output_1": "Living Room",
    "output_2": "Kitchen",
    "output_3": "Bathroom",
    "output_4": "Basement",
    **{f"output_{n}": "" for n in range(5, 9)},
    "tv_1": "4K",
    "tv_2": "1080p",
    "tv_3": "1080p",
    "tv_4": "1080p",
    **{f"tv_{n}": "4K" for n in range(5, 9)},
}


@pytest.fixture
async def fake(socket_enabled):
    fake, runner, port = await start_fake()
    fake.port = port
    yield fake
    await runner.cleanup()


async def _setup(hass: HomeAssistant, fake, command_port: int | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="02:00:00:00:12:34",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: fake.port,
            CONF_COMMAND_PORT: command_port or fake.command_port,
        },
        options=NAMES,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, fake) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake.port}
    )
    assert result["type"] == "create_entry", result
    assert result["result"].unique_id == "02:00:00:00:12:34"


async def test_config_flow_cannot_connect(hass: HomeAssistant, fake) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_entities_reflect_real_snapshot(hass: HomeAssistant, fake) -> None:
    await _setup(hass, fake)
    src = hass.states.get("select.hdmi_matrix_living_room_source")
    assert src.state == "Roku Ultra"
    assert src.attributes["options"] == ["Roku Ultra", "Onn 4K Pro", "Bathroom Roku", "Camera Wall"]
    assert set(src.attributes["shared_with"]) == {"Kitchen", "Bathroom", "Basement"}

    video = hass.states.get("sensor.hdmi_matrix_living_room_video")
    assert video.state == "1080p"
    assert video.attributes["held_back_by"] == "input EDID fixed at 1080p"
    assert video.attributes["edid_audio"] == "5.1ch"

    assert hass.states.get("select.hdmi_matrix_roku_ultra_video_edid").state == "1080p"
    assert hass.states.get("select.hdmi_matrix_onn_4k_pro_audio_edid").state == "5.1ch"
    assert hass.states.get("switch.hdmi_matrix_roku_ultra_hdr").state == "on"
    # Hidden ports create nothing.
    assert hass.states.get("select.hdmi_matrix_output5_source") is None
    # Deep color switches exist but are disabled by default.
    reg = er.async_get(hass)
    deep = [e for e in reg.entities.values() if e.entity_id.endswith("_30_bit_color")]
    assert deep and all(e.disabled_by is not None for e in deep)


async def test_route_output(hass: HomeAssistant, fake) -> None:
    await _setup(hass, fake)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.hdmi_matrix_living_room_source", "option": "Onn 4K Pro"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert fake.routing[0] == "1"  # 0-based input 2
    assert hass.states.get("select.hdmi_matrix_living_room_source").state == "Onn 4K Pro"
    video = hass.states.get("sensor.hdmi_matrix_living_room_video")
    assert video.state == "4K" and video.attributes["held_back_by"] is None
    assert fake.dropped == 0


async def test_all_tvs_one_command(hass: HomeAssistant, fake) -> None:
    await _setup(hass, fake)
    assert hass.states.get("select.hdmi_matrix_all_tvs_source").state == "Roku Ultra"
    fake.requests.clear()
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.hdmi_matrix_all_tvs_source", "option": "Onn 4K Pro"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert fake.commands == ["@T 04 01 #"]
    assert fake.routing == ["1"] * 8
    assert not [r for r in fake.requests if r.startswith("@PORT")]  # no per-TV fallback
    assert hass.states.get("select.hdmi_matrix_all_tvs_source").state == "Onn 4K Pro"
    assert hass.states.get("select.hdmi_matrix_basement_source").state == "Onn 4K Pro"
    assert fake.dropped == 0


async def test_all_tvs_falls_back_per_tv(hass: HomeAssistant, fake) -> None:
    """Command port unreachable: the named TVs are still switched one at a time."""
    closed = fake.command_port
    fake.tcp.close()
    await fake.tcp.wait_closed()
    fake.tcp = None
    await _setup(hass, fake, command_port=closed)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.hdmi_matrix_all_tvs_source", "option": "Camera Wall"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert fake.routing[:4] == ["3"] * 4 and fake.routing[4:] == ["0"] * 4
    assert hass.states.get("select.hdmi_matrix_all_tvs_source").state == "Camera Wall"
    assert fake.dropped == 0


async def test_all_tvs_shows_nothing_when_mixed(hass: HomeAssistant, fake) -> None:
    fake.routing[1] = "2"
    await _setup(hass, fake)
    assert hass.states.get("select.hdmi_matrix_all_tvs_source").state == "unknown"


async def test_dropped_connection_is_retried(hass: HomeAssistant, fake) -> None:
    await _setup(hass, fake)
    fake.reset_next = 1
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.hdmi_matrix_living_room_source", "option": "Camera Wall"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert fake.routing[0] == "3"
    assert hass.states.get("select.hdmi_matrix_living_room_source").state == "Camera Wall"


async def test_edid_changes_only_touch_one_field(hass: HomeAssistant, fake) -> None:
    await _setup(hass, fake)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.hdmi_matrix_onn_4k_pro_audio_edid", "option": "7.1ch"},
        blocking=True,
    )
    assert fake.edid[1] == "2100004"
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.hdmi_matrix_roku_ultra_hdr"}, blocking=True
    )
    assert fake.edid[0] == "1000002"
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.hdmi_matrix_roku_ultra_video_edid", "option": "4K60 4:4:4"},
        blocking=True,
    )
    assert fake.edid[0] == "4000002"
    await hass.async_block_till_done()
    assert hass.states.get("sensor.hdmi_matrix_kitchen_video").state == "4K (TV may not display)"
    # Untouched inputs stayed exactly as the real matrix had them.
    assert fake.edid[2:] == ["2100001", "3010001", "3010001", "3010001", "3010001", "3010001"]


async def test_offline_then_recovers(hass: HomeAssistant, fake) -> None:
    entry = await _setup(hass, fake)
    coordinator = entry.runtime_data
    fake.fail_next = 1
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("select.hdmi_matrix_living_room_source").state == STATE_UNAVAILABLE
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("select.hdmi_matrix_living_room_source").state == "Roku Ultra"


async def test_options_flow(hass: HomeAssistant, fake) -> None:
    entry = await _setup(hass, fake)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    new = {**NAMES, "input_5": "Roku Ultra 4K"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], new)
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    src = hass.states.get("select.hdmi_matrix_living_room_source")
    assert "Roku Ultra 4K" in src.attributes["options"]


async def test_diagnostics_redacts_address(hass: HomeAssistant, fake) -> None:
    from custom_components.jtech_h20.diagnostics import async_get_config_entry_diagnostics

    entry = await _setup(hass, fake)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = str(diag)
    assert "127.0.0.1" not in text and "02:00:00:00:12:34" not in text
    assert diag["raw_edid"][1] == "1100002"
    assert diag["state"]["routing"][1] == 1


async def test_reconfigure_same_matrix(hass: HomeAssistant, fake) -> None:
    """Same matrix at a new address (simulated by a second fake with the same MAC)."""
    entry = await _setup(hass, fake)
    moved, runner, port = await start_fake()
    try:
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == "form"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: port}
        )
        assert result["type"] == "abort" and result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_PORT] == port
        await hass.async_block_till_done()
        assert hass.states.get("select.hdmi_matrix_living_room_source").state == "Roku Ultra"
    finally:
        await runner.cleanup()


async def test_reconfigure_rejects_other_matrix(hass: HomeAssistant, fake) -> None:
    entry = await _setup(hass, fake)
    other, runner, port = await start_fake()
    try:
        other.mac = "02:00:00:00:99:99"
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: port}
        )
        assert result["errors"] == {"base": "wrong_device"}
        assert entry.data[CONF_PORT] == fake.port
    finally:
        await runner.cleanup()
