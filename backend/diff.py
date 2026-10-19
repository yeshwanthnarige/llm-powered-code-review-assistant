import re


def parse_diff(diff: str) -> list[dict]:
    """Parse unified text diffs, preserving new-side line numbers and added lines."""
    files = []
    current = None
    old_left = new_left = 0
    old_number = new_number = 0
    in_hunk = False
    for raw in diff.splitlines():
        if raw.startswith('diff --git '):
            if in_hunk and (old_left or new_left):
                raise ValueError('Incomplete diff hunk. Paste the complete unified diff.')
            current = None
            in_hunk = False
        if raw.startswith('+++ ') and not in_hunk:
            path = raw[4:].split('\t')[0]
            if path.startswith('b/'):
                path = path[2:]
            if path == '/dev/null':
                current = None
                continue
            if path.startswith('/') or '..' in path.split('/'):
                raise ValueError('Diff contains an invalid file path.')
            current = {'path': path, 'lines': [], 'added_lines': []}
            files.append(current)
            continue
        if raw.startswith('@@ '):
            if in_hunk and (old_left or new_left):
                raise ValueError('Incomplete diff hunk.')
            match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', raw)
            if not match:
                raise ValueError('Malformed diff hunk header.')
            old_number, old_count, new_number, new_count = match.groups()
            old_number, new_number = int(old_number), int(new_number)
            old_left = int(old_count) if old_count is not None else 1
            new_left = int(new_count) if new_count is not None else 1
            in_hunk = bool(old_left or new_left)
            continue
        if not in_hunk or raw.startswith('\\ No newline'):
            continue
        kind = raw[:1]
        if kind not in {'+', '-', ' '}:
            raise ValueError('Invalid unified diff line.')
        number = None if kind == '-' else new_number
        if current is not None:
            current['lines'].append({'kind': kind, 'number': number, 'text': raw[1:]})
            if kind == '+':
                current['added_lines'].append(new_number)
        if kind != '+':
            old_number += 1
            old_left -= 1
        if kind != '-':
            new_number += 1
            new_left -= 1
        if old_left < 0 or new_left < 0:
            raise ValueError('Diff hunk counts do not match its contents.')
        in_hunk = bool(old_left or new_left)
    if in_hunk:
        raise ValueError('Incomplete diff hunk. Paste the complete unified diff.')
    if not files or not any(f['added_lines'] for f in files):
        raise ValueError('Provide a unified text diff with at least one added line.')
    return files
