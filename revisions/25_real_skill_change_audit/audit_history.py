"""Summarize edit primitives in pinned public SKILL.md histories without copying content."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import subprocess

REVISION = Path(__file__).resolve().parent
FIELDS = ('repository', 'commit', 'parent', 'authored_at', 'path', 'added_lines',
          'deleted_lines', 'hunks', 'deletion_present', 'mixed_replacement_hunk',
          'similar_line_replacement_candidate', 'line_relocation_candidate')


def git(repo, *args):
    return subprocess.run(['git', *args], cwd=repo, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def normalize(line):
    line = re.sub(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)', '', line.strip().lower())
    return re.sub(r'\s+', ' ', line)


def parse_zero_context(diff):
    hunks, current = [], None
    for line in diff.splitlines():
        if line.startswith('@@'):
            current = {'removed': [], 'added': []}
            hunks.append(current)
        elif current is not None and line.startswith('-') and not line.startswith('---'):
            current['removed'].append(line[1:])
        elif current is not None and line.startswith('+') and not line.startswith('+++'):
            current['added'].append(line[1:])
    return hunks


def edit_flags(hunks):
    removed = [normalize(line) for hunk in hunks for line in hunk['removed'] if normalize(line)]
    added = [normalize(line) for hunk in hunks for line in hunk['added'] if normalize(line)]
    mixed = [hunk for hunk in hunks if hunk['removed'] and hunk['added']]
    similar = any(SequenceMatcher(None, normalize(left), normalize(right)).ratio() >= .55
                  and normalize(left) != normalize(right)
                  for hunk in mixed for left in hunk['removed'] for right in hunk['added']
                  if normalize(left) and normalize(right))
    return {
        'deletion_present': bool(removed),
        'mixed_replacement_hunk': bool(mixed),
        'similar_line_replacement_candidate': similar,
        'line_relocation_candidate': bool(set(removed) & set(added)),
    }


def modified_skill_paths(repo, parent, commit):
    output = git(repo, 'diff', '--name-status', '--diff-filter=M', parent, commit,
                 '--', ':(glob)**/SKILL.md')
    return [line.split('\t', 1)[1] for line in output.splitlines() if line.startswith('M\t')]


def audit_repository(repo, entry):
    if git(repo, 'rev-parse', entry['commit']).strip() != entry['commit']:
        raise ValueError(f"Pinned commit is unavailable for {entry['name']}")
    remote = git(repo, 'remote', 'get-url', 'origin').strip().removesuffix('/')
    expected = entry['url'].removesuffix('.git')
    if remote.removesuffix('.git') != expected:
        raise ValueError(f"Remote mismatch for {entry['name']}")
    commits = git(repo, 'rev-list', '--first-parent', '--reverse', entry['commit']).splitlines()
    rows = []
    for commit in commits[1:]:
        parent = git(repo, 'rev-parse', commit + '^1').strip()
        authored = git(repo, 'show', '-s', '--format=%aI', commit).strip()
        for path in modified_skill_paths(repo, parent, commit):
            diff = git(repo, 'diff', '--unified=0', '--no-color', parent, commit, '--', path)
            hunks = parse_zero_context(diff)
            added = sum(len(hunk['added']) for hunk in hunks)
            deleted = sum(len(hunk['removed']) for hunk in hunks)
            rows.append({'repository': entry['name'], 'commit': commit, 'parent': parent,
                         'authored_at': authored, 'path': path, 'added_lines': added,
                         'deleted_lines': deleted, 'hunks': len(hunks), **edit_flags(hunks)})
    return rows, len(commits)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=REVISION / 'repositories.json')
    parser.add_argument('--output', type=Path, default=REVISION / 'results')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    rows, traversed = [], {}
    for entry in config['repositories']:
        current, count = audit_repository(args.repo_root / entry['name'], entry)
        rows.extend(current)
        traversed[entry['name']] = count
    args.output.mkdir(parents=True, exist_ok=True)
    table = args.output / 'skill_file_edits.csv'
    with table.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    categories = {field: sum(bool(row[field]) for row in rows) for field in FIELDS[-4:]}
    by_repository = {}
    for entry in config['repositories']:
        group = [row for row in rows if row['repository'] == entry['name']]
        by_repository[entry['name']] = {
            'modified_skill_file_edits': len(group),
            'commits_with_modified_skill_files': len({row['commit'] for row in group}),
            'category_file_edit_counts': {
                field: sum(bool(row[field]) for row in group) for field in FIELDS[-4:]},
        }
    result = {
        'status': 'completed', 'snapshot_timing': config['status'],
        'repositories': len(config['repositories']), 'mainline_commits_traversed': traversed,
        'modified_skill_file_edits': len(rows),
        'repositories_with_modified_skill_files': len({row['repository'] for row in rows}),
        'category_file_edit_counts': categories,
        'by_repository': by_repository,
        'category_scope_warning': 'Heuristic structural candidates; not semantic ground truth.',
        'r24_operators_changed_after_audit': False,
        'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
        'table_sha256': hashlib.sha256(table.read_bytes()).hexdigest(),
    }
    (args.output / 'completion.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
