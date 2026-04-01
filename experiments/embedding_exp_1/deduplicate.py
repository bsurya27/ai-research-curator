import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # project root
from scraping.utils import deduplicate

path = Path(__file__).parent / 'data' / 'labeled_dataset.jsonl'

items = [json.loads(l) for l in open(path)]
print(f'Before: {len(items)}')
items = deduplicate(items)
print(f'After: {len(items)}')

with open(path, 'w') as f:
    for item in items:
        f.write(json.dumps(item) + '\n')

print('Done.')