import argparse
from functions import get_paths
from db import create_db, populate_db


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description="Populate database from selected folder")
    ap.add_argument('folder', nargs='?', default='./music', help="music folder (default: ./music)")
    ap.add_argument('--workers', type=int, help="parallel processes (default: CPU count - 1)")
    args = ap.parse_args()
 
    paths = get_paths(args.folder)
    if not paths:
        raise SystemExit(f"No audio files found in {args.folder}")
 
    conn = create_db()
    populate_db(conn=conn, paths=paths, workers=args.workers)
    conn.close()