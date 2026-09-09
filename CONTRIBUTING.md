# Contributing

Use synthetic account, child, token, and activity fixtures. Never commit credentials, preference files, Keychain exports, real API responses, virtual environments, or caches. Run `python scripts/test.py` before submitting changes; use `--upstream` for reviewed-client compatibility checks. No live account writes belong in CI.

Source workspace maintainers run `python release/scripts/test.py --root skills` and `python release/scripts/package.py --skills skills --output dist/nara-baby-portable.zip`. Extract the archive and run its tests before release. The package script uses an explicit file allowlist and records per-file SHA-256 checksums.

Review the source and update both digest pins deliberately when changing the upstream revision. Supply only that reviewed source to compatibility tests. Preserve child selection on token refresh, fail closed on ambiguous names, and test timezone boundaries. Never infer successful account discovery from an empty malformed response.

Keep hosted-agent proposals separate from working backends. New credential backends require explicit selection, sanitized errors, and tests proving there is no silent downgrade to plaintext.
