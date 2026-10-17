import argparse
import os
import time
from collections import Counter
from db import create_db
from functions import process_song, get_matches, best_matches, record_snippet, mmss


MIN_SCORE = 15 
MIN_RATIO = 2.0

def default_input_device():
    import sounddevice as sd
    info = sd.query_devices(kind='input')
    return info.get('index', sd.default.device[0])

def main():
    ap = argparse.ArgumentParser(description="Recognize a song from the microphone or from an audio file.")
    ap.add_argument('--file', help="recognize song from audio file")
    ap.add_argument('--start', type=float, default=0, help="start the clip at this second")
    ap.add_argument('--seconds', type=float, default=5, help="analyzed length (default: 5)")
    ap.add_argument('--device', type=int, help="input device id (default: system default, see --devices)")
    ap.add_argument('--devices', action='store_true', help="list audio devices and exit")
    args = ap.parse_args()

    if args.devices:
        import sounddevice as sd
        print(sd.query_devices())
        return

    if args.file:
        if not os.path.exists(args.file):
            ap.error(f"file not found: {args.file}")
        path, offset = args.file, args.start
    else:
        device = args.device if args.device is not None else default_input_device()
        print(f"Recording {args.seconds:.0f}s from device {device}")
        record_snippet(device=device, duration=args.seconds, sr=22050, filename='snippet.wav')
        path, offset = 'snippet.wav', 0
        

    start = time.time()
    hashes = process_song(path=path, duration=args.seconds, offset=offset)
    conn = create_db()

    try:
        matches = get_matches(conn, h_snippet=hashes)
    finally:
        conn.close()

    results = best_matches(matches, n=5)
    elapsed = time.time() - start

    if not results:
        print("No candidates (silent clip or empty database).")
        return

    runner_up = results[1][0] if len(results) > 1 else 0
    confident = results[0][0] >= MIN_SCORE and results[0][0] >= MIN_RATIO * max(runner_up, 1)

    print(f"\n{'score':>6}  {'at':>5}  track")
    for i, (score, name) in enumerate(results):
        position = max(0.0, Counter(matches[name]).most_common(1)[0][0])
        print(f"{score:>6}  {mmss(position):>5}  {name}")

    if not confident:
        print("\nNo confident match. Try a longer or louder clip.")

    print(f"\nTime: {elapsed:.2f} s")


if __name__ == '__main__':
    main()