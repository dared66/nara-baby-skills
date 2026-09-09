# Muse: native credential and request route

Target: Meta Muse at muse.ai. Researched 2026-09-08. Status: instructions for adapting inside Muse; no native Muse adapter has been executed or validated from this local workspace.

## Verified platform design

Meta's [security architecture](https://research.meta.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse) describes a Linux runtime separated from credential storage. `hatch-authd` manages credentials; Sentinel authorizes network traffic and substitutes credential surrogates at the network boundary. A private user interface captures website usernames/passwords outside the conversation. Built-in connectors can run in separately privileged workers. Meta also says Muse can create custom API/CLI connectors. The article does not publish the custom connector command syntax, credential-registration API, or prove that every built-in privilege is available to user-created connectors.

## Instructions for the agent running inside Muse

Use this hosted route before the local Keychain onboarding steps. Do not run the macOS rebuild or try to read the Mac's Keychain from Muse.

1. Inspect your available native tools and built-in help for custom connector creation, private credential setup, authenticated requests, and token-reference handling. Use exact interfaces exposed by your runtime; `hatch-authd`, `privsep`, and Sentinel are architecture names, not commands supplied by this skill. Do not invent socket calls or privileged worker access.
2. If custom connectors support the required Nara login flow, invoke the supported private credential-entry UI for the Nara service/account. Reuse a suitable existing entry by reference with the user's authorized scope. Keep real passwords out of chat, scripts, and configuration.
3. Route Nara requests through the supported native request mechanism. Verify whether it can substitute credentials in the login JSON body and protect the returned ID token. Support that token in both bearer headers and RTDB auth query parameters. If only header substitution or browser filling is available, report the missing capability; do not extract passwords or tokens through the browser.
4. Use the host's supported permission flow for the specific Nara/Firebase destinations and requested operations. Do not request broad network or credential access. Inspect the reviewed Nara source for exact paths; preserve source-hash verification when loading it.
5. Reuse the response parser and timezone calculations. Fetch family/child data read-only. Ask the user for timezone and intended child, verify the name-to-key mapping, and retain only those non-secret preferences. Confirm success from actual responses.
6. Test token renewal, denied/revoked access, and error redaction. A denial must not trigger plaintext fallback. Do not claim that credentials are hidden from the runtime unless the actual custom-connector mechanism provides that boundary.

## Required adaptation to this bundle

The current local `Transport` disables inherited proxy configuration (`trust_env=False`), and `connected_client` expects real credentials and an ID token in memory. They are macOS implementations, not a Muse network adapter. Keep them intact for local use. Implement a separate native authentication/request path that respects Muse's proxy and credential-reference contract. Do not bypass Sentinel or simply turn on arbitrary environment trust without the host's documented configuration.

The Linux Python pieces (parsing, time conversion, and non-secret preferences) are reusable; the macOS-only rebuild and credential library are not the hosted installation path. A native authenticated-request adapter may replace login entirely rather than implementing `load_record()` as a password-returning function.

If the needed interfaces are not exposed, return `needs_hosted_adapter` with the concrete missing capability. Offer the Instinct proposal's explicitly selected file fallback only if the host permits it and the user chooses it; no such fallback is implemented by this document.

## Handoff prompt for Muse

> Adapt this Nara skill to your native credential and network system. First inspect your supported custom-connector tools/help. Use your private credential-entry UI and credential references where available; never ask me to paste a password into chat. Verify support for Firebase JSON-body login and returned-token handling before implementing. Preserve Sentinel enforcement, the corrected activity parser, explicit first-run child selection, and my timezone. Start with read-only verification and report unsupported capabilities precisely.
