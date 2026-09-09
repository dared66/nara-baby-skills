# Third-party components

The MIT license in this bundle covers its original adapter, skill instructions, tests, and tooling. It does not relicense third-party software.

- Nara Python client: https://github.com/jfchenier/nara-baby-tracker-api
- Reviewed revision: `8f0371cd05d112e3217e594473d0e1dd87615b61`
- `nara.py` SHA-256: `fc8358a285544de343f008b80e9056cb31c7833cd1d7d5c9a1e3b3d4fca3e8a0`

The upstream source is not included. Rebuild downloads it separately. No license file was found in the reviewed checkout; clarify upstream permissions before redistributing that code. The small contract fixture in these tests is an original test double, not a vendored client.

Requests and keyring are installed separately with their own dependencies and licenses. Direct dependency versions are pinned; transitive dependencies are not fully locked. Public Firebase project identifiers and endpoint names are connection metadata, not account credentials. Nara's service availability and schemas may change independently of this release.
