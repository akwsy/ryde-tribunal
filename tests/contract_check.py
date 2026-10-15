"""Compatibility entry point for the Node-based OpenAPI response validator."""
import argparse
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000/api/v1')
    parser.add_argument('--case-id')
    parser.add_argument('--contract', default='shared/openapi.yaml')
    parser.add_argument('--payload-file')
    parser.add_argument('--policy-file')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    command = ['node', str(root / 'tests/contract_check.mjs'), '--base-url', args.base_url,
               '--contract', str(Path(args.contract).resolve())]
    if args.case_id:
        command.extend(['--case-id', args.case_id])
    if args.payload_file:
        command.extend(['--payload-file', str(Path(args.payload_file).resolve())])
    if args.policy_file:
        command.extend(['--policy-file', str(Path(args.policy_file).resolve())])
    return subprocess.run(command, cwd=root, check=False).returncode


if __name__ == '__main__':
    sys.exit(main())
