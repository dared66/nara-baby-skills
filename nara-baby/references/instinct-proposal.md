# Instinct: research and implementation proposal

Researched 2026-09-08. Target: the hosted assistant at instinct.com operated by Spear Street Technology, not AMD Instinct or Merit-Systems/OpenInstinct. Status: proposal, not a tested connector.

## What is established

[Instinct's official site](https://instinct.com/) describes an assistant connecting to applications and devices and using a phone/computer. Its [privacy policy](https://instinct.com/privacy-policy), revised August 26, 2026, explicitly discusses users providing third-party usernames/passwords so the assistant can sign in. Neither page documents a vault SDK, secret-reference syntax, custom connector authentication API, or guarantees that custom Python code can obtain scoped credentials without exposing them to the model.

I searched the official instinct.com and instinct.co domains for vault, credentials, password, and tool/API documentation. No public technical contract was found. This is a limit of the research, not proof the installed product lacks a vault. OpenInstinct is a separate project; its code cannot establish hosted Instinct behavior. Unofficial command examples are not an implementation specification.

## Proposed approach

First, run a capability check inside the user's actual Instinct session using its exposed tools and built-in help. Do not run guessed commands, enumerate saved secrets, or ask for credentials during this check. Find out whether it offers:

- A private credential-entry UI or link, plus a reusable service/account reference.
- Authentication for arbitrary approved API requests, rather than browser filling alone.
- Credential substitution into a JSON request body, and management of tokens returned by a login response.
- A supported request executor, proxy, or scoped subprocess secret injection mechanism.
- Persistent storage for non-secret child/timezone preferences and revocation of this integration's access.

If available, reuse that native mechanism. The desired flow is: user enters Nara login privately; the credential store authenticates an approved request; the script receives activity results or permitted token references. Keep credentials out of conversation, source files, and the exported skill. A browser-fill-only vault is insufficient evidence for this Nara Firebase API flow. Do not scrape a filled password field to turn browser access into API credentials.

If native API authentication is unavailable but the host supports scoped runtime secrets, use its documented mechanism for just the Nara subprocess. This is a deliberate hosted mode, not a silent fallback from a denied or locked credential store.

If neither exists, offer a user-selected plaintext file backend as the compatibility option. That backend is proposed, not currently implemented: the user supplies the file via a private host-supported file/setup surface; it lives outside the skill/repository with directory mode 0700 and file mode 0600; the script reads it directly; exports exclude it. POSIX permissions do not hide it from the same-user agent or host administrator. Explain that difference when the user chooses storage. No production credentials should be copied from a local device merely to test availability.

## Nara implementation work after capability discovery

Introduce a hosted authentication/request adapter alongside the current macOS adapter, rather than replacing Keychain globally. Preserve the tested response parser, child checks, time conversion, and fixed error outputs. Keep the credentials API narrow; do not require a brokered backend to return a real password if it can execute authentication itself.

Nara login sends email/password in JSON to Firebase Identity Toolkit, then uses a returned ID token in a bearer header and RTDB query parameter. The adapter must support all three placements and avoid exposing login-response tokens. Confirm the host supports this flow before advertising compatibility. Keep child selection explicit on first use and preserve it across token renewal.

Read-only acceptance: private login entry succeeds; the expected family and children appear; timezone and verified child selection persist; no credentials/tokens appear in output, errors, or files; revocation fails cleanly without switching storage. Test writes only for a specific user-requested activity. No server on the user's Mac is proposed.

## Handoff prompt for Instinct

> Read the Nara skill and this proposal. Inspect your available credential, connector, and network tools using built-in help. Report the actual supported commands/interfaces for private credential entry and authenticated API requests, including JSON-body injection and handling returned Firebase tokens. Do not ask for passwords in chat, read existing secret values, or guess undocumented commands. Propose the smallest adapter using your native system. If only browser filling or plaintext storage is available, state that limitation before configuring Nara. Once supported, onboard credentials, timezone, and a verified child choice, then perform a read-only check.

The next evidence needed is Instinct's own capability/help output; this proposal does not require granting a local agent access to Instinct or sending a message to anyone.
