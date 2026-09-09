#!/usr/bin/env python3
"""Build a deterministic source bundle using an explicit file allowlist."""
import argparse
import hashlib
from pathlib import Path
import zipfile

RELEASE_FILES = ('README.md', 'LICENSE', 'SECURITY.md', 'CONTRIBUTING.md', 'THIRD_PARTY.md', '.gitignore', '.github/workflows/tests.yml', 'scripts/test.py', 'scripts/package.py')
SKILLS = {
    'keychain-credentials': ('SKILL.md', 'pyproject.toml', 'scripts/skill_credentials.py', 'tests/test_credentials.py'),
    'nara-baby': ('SKILL.md', 'agents/openai.yaml', 'references/api.md', 'references/portability.md', 'references/muse.md', 'references/instinct-proposal.md', 'scripts/nara_cli.py', 'scripts/nara_client.py', 'scripts/nara_keychain.py', 'scripts/nara_timezone.py', 'scripts/nara_config.py', 'scripts/run.py', 'scripts/rebuild.py', 'tests/test_keychain_client.py', 'tests/test_timezone.py', 'tests/test_time_conversion.py', 'tests/test_release_safety.py', 'tests/fixtures/upstream_contract.py'),
}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--skills', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    release = Path(__file__).resolve().parents[1]
    files = {name: (release / name).read_bytes() for name in RELEASE_FILES}
    for skill, names in SKILLS.items():
        for name in names:
            path = args.skills / skill / name
            if path.is_symlink():
                p.error('Symlinks cannot be packaged')
            files[f'{skill}/{name}'] = path.read_bytes()
    files['SHA256SUMS'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(files.items())).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(args.output.suffix + '.sha256').write_text(f'{digest}  {args.output.name}\n')
    print(f'Built {len(files)} files; SHA-256 {digest}')

if __name__ == '__main__':
    main()
