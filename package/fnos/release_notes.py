"""Maintain a single fnOS download section without replacing release notes."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from build import asset_name

START = '<!-- trailsnap-fnos-download:start -->'
END = '<!-- trailsnap-fnos-download:end -->'


def update_notes(body: str, tag: str, repository: str) -> str:
    if not tag.startswith('v') or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid release tag or repository')
    filename = asset_name(tag[1:])
    base = f'https://github.com/{repository}/releases/download/{tag}/'
    section = '\n'.join([START, '### 飞牛 fnOS', '',
        f'- [下载飞牛 x86 安装包]({base}{filename})',
        f'- [SHA256 校验文件]({base}{filename}.sha256)',
        '- [安装与使用教程](https://trailsnap.cn/docs/guide/fnos)', END])
    pattern = re.escape(START) + r'.*?' + re.escape(END)
    body = re.sub(pattern, '', body, flags=re.S).rstrip()
    return (body + '\n\n' if body else '') + section + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--repository', required=True)
    args = parser.parse_args()
    result = subprocess.run(['gh', 'release', 'view', args.tag, '--repo', args.repository,
                             '--json', 'body', '--jq', '.body'],
                            check=True, capture_output=True, text=True, encoding='utf-8')
    notes = update_notes(result.stdout, args.tag, args.repository)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'release-notes.md'
        path.write_text(notes, encoding='utf-8')
        subprocess.run(['gh', 'release', 'edit', args.tag, '--repo', args.repository,
                        '--notes-file', str(path)], check=True)


if __name__ == '__main__':
    main()
