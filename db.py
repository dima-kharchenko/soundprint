import time
import os
import sqlite3

from tqdm import tqdm
from multiprocessing import Pool, cpu_count
from functions import process_song


def create_db(path='fingerprints.db'):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = MEMORY")
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS songs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS fingerprints (
        hash INTEGER NOT NULL,
        song_id INTEGER NOT NULL,
        offset INTEGER NOT NULL,
        FOREIGN KEY (song_id) REFERENCES songs(id)
    );
    """)

    return conn

def build_index(conn):
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON fingerprints(hash)")
    conn.commit()

def song_exists(conn, name):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM songs WHERE name = ?",
        (name,)
    )
    return cursor.fetchone() is not None

def save_song(conn, name, hashes):
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO songs (name) VALUES (?)",
        (name,)
    )
    song_id = cursor.lastrowid

    cursor.executemany(
        "INSERT INTO fingerprints (hash, song_id, offset) VALUES (?, ?, ?)",
        [(h, song_id, t) for h, t in hashes]
    )

    conn.commit()

def process_worker(path):
    name = os.path.basename(path)
    hashes = process_song(path=path)
    return name, hashes

def populate_db(conn, paths, workers=None):
    if workers is None:
        workers = max(1, cpu_count() - 1)

    seen = set()
    to_process = []
    for p in paths:
        name = os.path.basename(p)
        if song_exists(conn, name) or name in seen:
            continue
        seen.add(name)
        to_process.append(p)
 
    start = time.time()
    with Pool(workers) as pool:
        results = list(tqdm(pool.imap(process_worker, to_process), total=len(to_process)))
    print(f"pool: {(time.time() - start):.2f} s")
 
    start = time.time()
    for name, hashes in tqdm(results):
        save_song(conn, name, hashes)
    build_index(conn)
    print(f"db: {(time.time() - start):.2f} s")