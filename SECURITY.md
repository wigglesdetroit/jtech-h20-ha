# Security

## Reporting a problem

Please report security issues privately through GitHub's
**Security → Report a vulnerability** on this repository, not in a public issue.
I'll acknowledge the report, fix it in the open, and credit you in the release notes
unless you'd rather not be named.

## What this integration touches

- It makes plain HTTP `GET` requests to one device on your local network: the matrix
  at the address you configure.
- It stores no passwords, tokens or API keys. The H20's web interface has none to store.
- It opens no ports and serves no web pages or APIs of its own.
- It can change routing and EDID settings only. It has no code for firmware upload,
  network or password changes, or factory reset.

## Known limitation of the hardware

The JTECH-8X8-H20's web interface has no server-side authentication. Its login page is
checked only in the browser. Anything on your network can change the matrix, with or
without this integration. Keep the matrix on a trusted network and never forward its web
port to the internet.
