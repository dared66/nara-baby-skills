# Security boundaries

Credentials live in macOS Keychain under a service/account pair. Python retrieves them inside the short-lived API process. There is no plaintext-file or environment fallback, raw-secret CLI, or background server. Existing passwords visible in Apple's Passwords app are not automatically the same generic Keychain entry used by this adapter.

This does not isolate secrets from code or an agent controlling that process. Secrets exist in process memory; clearing references is not guaranteed zeroization. Output/log suppression is process-wide, so use a dedicated subprocess rather than a multithreaded host. A locked or denied Keychain should be unlocked or authorized, not silently replaced.

HTTP requests use verified HTTPS, approved Nara hostnames, bounded timeouts, no redirects, and no inherited proxy or .netrc configuration. Read authentication can refresh once; writes are never automatically retried. Creation helpers use non-atomic multi-location writes. Edits use a fresh sync record and the existing ID in the sync queue; they verify returned values but do not provide a server-side compare-and-swap guarantee against concurrent caregiver edits. Read back a known activity before retrying an uncertain write.

Activity output contains personal data by design. Identifier filtering is not anonymization and cannot remove sensitive information embedded in free-text notes. Keep output local to the authorized task. `--include-internal` explicitly exposes identifiers for diagnostics; do not attach raw output to public issues.

For vulnerability reports, use a private reporting channel offered by the repository host. If none is configured, request a private contact without posting credentials, child records, identifiers, or reproduction logs containing personal data.
