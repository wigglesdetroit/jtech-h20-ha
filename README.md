# J-Tech HDMI Matrix (8x8 H20) for Home Assistant

> **Status: beta (0.2.0).** Tested against a fake matrix that copies a real unit's
> responses; real-hardware testing is in progress.

Local control of the **J-Tech Digital JTECH-8X8-H20** (JTD-279) 4K HDMI 2.0 matrix,
through the matrix's own web interface (plus one command on its TCP command port).
No cloud, no serial cable, no extra software.

## What you get

For each TV output:

- **Source picker** (`select`): pick which input the TV shows. Reflects changes made
  anywhere else (front panel, IR remote, the web page) within a few seconds.
- **Video sensor** (`sensor`): the resolution that output is getting (`1080p` / `4K`),
  with attributes for the source, EDID video and audio settings, HDR, and what is
  holding it back, if anything.

For the whole matrix:

- **All TVs source** (`select`): send one input to every output in a single step, like the
  front panel's ALL button. Shows the input when every named TV is on the same one.

For each input:

- **EDID video** (`select`): 1080p, 4K30, 4K60 4:2:0, 4K60 4:4:4, or copy from TV1–TV8
- **EDID audio** (`select`): 2.0, 5.1 or 7.1 channels
- **HDR / 3D** (`switch`), plus 30/36/48-bit deep color (disabled by default)

Each EDID change reads the input's current settings first and changes only the field
you touched.

## Install

1. In HACS, add this repository as a custom repository (type **Integration**) and download it.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → J-Tech HDMI Matrix**, enter the
   matrix's IP address.
4. Open the integration's **Configure** to name your inputs and outputs (leave a name blank
   to hide that port) and to say which TVs are 4K and which are 1080p.

## How it talks to the matrix

The H20's web page loads its state from `GET /HDMI_MUX.js`, which returns every output's
routing, every input's EDID, and the port names in one response, with no login. Changes are
plain `GET` requests the page itself makes:

| Action | Request |
| --- | --- |
| Route output `o` to input `i` | `/@PORT<o>=<i>.<random>` |
| Set input `n`'s EDID | `/@EDID<n>=<7 characters>.<random>` |

The EDID string is `[video][HDR][3D][30-bit][36-bit][48-bit][audio]`, where video is
`1`–`4` for the fixed modes or `5`–`C` to copy TV1–TV8, and audio is `1`/`2`/`4` for
2.0/5.1/7.1.

**All TVs source** uses the matrix's text command port instead (TCP 5000, the same command
set as its RS232 port): `@T 04 <in1> <in2> … <in8> #` sets the input for all 8 outputs
at once (0-based, `00` = input 1), so `@T 04 01 01 01 01 01 01 01 01 #` puts input 2 on every
output. Afterwards the integration reads the routing back and switches any
named TV that didn't follow, one at a time over the web interface, so it still works if the
command port is unreachable. It switches all 8 outputs, including hidden ones.

The matrix only answers one request at a time; simultaneous requests get dropped. The
integration sends everything, web requests and commands alike, through a single queue and
polls every 5 seconds. Avoid running other tools that poll the matrix at the same time.

## What it will never do

The matrix's web page can also upload firmware, change the IP address and password, and
reset to factory defaults. This integration has no code for any of that, on purpose.

## Limits

- The matrix reports its **settings**, not the live signal. The video sensor is worked out
  from the input's EDID setting and the TV types you enter, not measured.
- Tested against a JTECH-8X8-H20 (web title `JTD-279`). Other J-Tech models use different
  protocols. The older 10.2 Gbps H20 and the 4x4 models won't work.
- The matrix's web page has no real authentication, so anything on your network can change
  its routing. That's the matrix, not this integration.

## Development

```bash
pip install pytest-homeassistant-custom-component
pytest
```

The tests run a real Home Assistant instance against `tests/fake_matrix.py`, a fake H20
that answers the way the real unit does, including dropping concurrent requests.

## Credits

Built by [wigglesdetroit](https://github.com/wigglesdetroit) with Claude. The protocol was
mapped from the matrix's own web interface, and the integration is tested on a real
JTECH-8X8-H20 before each release. Security reports: see [SECURITY.md](SECURITY.md).
