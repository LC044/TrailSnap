"""Import a published feed locally or sync GitHub, then inspect a historical journey."""
import argparse
import json
from pathlib import Path

from railway.history_cache import HistoryCache, fetch_feed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', help='Cache SQLite path (defaults to application data directory)')
    parser.add_argument('--feed-dir', type=Path, help='Import a local data/feed directory')
    parser.add_argument('--sync', action='store_true', help='Fetch the configured GitHub feed')
    parser.add_argument('--train')
    parser.add_argument('--date')
    parser.add_argument('--departure')
    parser.add_argument('--arrival')
    args = parser.parse_args()
    cache = HistoryCache(args.db)
    if args.feed_dir:
        manifest = json.loads((args.feed_dir/'manifest.json').read_text(encoding='utf-8'))
        cache.sync(manifest, lambda file: (args.feed_dir/file).read_bytes())
    elif args.sync:
        fetch_feed(cache=cache)
    result = cache.status()
    if args.train:
        if not args.date:
            parser.error('--train requires --date')
        result['query'] = cache.resolve(args.train, args.date, args.departure, args.arrival)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
