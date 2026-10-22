import io
import os
import tempfile
import time
import wave
import streamlit as st
import db as db_module

from collections import Counter
from pathlib import Path
from db import create_db, populate_db
from functions import get_paths, process_song, get_matches, best_matches, get_spectrogram, mmss


CLIP_SECONDS = 10 
MIN_SECONDS = 3
MIN_SCORE = 15
MIN_RATIO = 2.0

def title_of(name):
    return Path(name).stem

def wav_seconds(data):
    try:
        with wave.open(io.BytesIO(data)) as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return None

def library_stats(conn):
    n_songs = conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
    n_hashes = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
    return n_songs, n_hashes

def analyze(data, suffix, offset, duration):
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
    try:
        D, _ = get_spectrogram(path=tmp.name, duration=duration, offset=offset)
        if D.max() == D.min():
            return {'n_hashes': 0, 'candidates': []}
        t0 = time.time()
        hashes = process_song(path=tmp.name, duration=duration, offset=offset)
    finally:
        os.unlink(tmp.name)

    conn = create_db()
    try:
        matches = get_matches(conn, h_snippet=hashes)
    finally:
        conn.close()

    candidates = []
    for score, name in best_matches(matches, n=5):
        best_offset = Counter(matches[name]).most_common(1)[0][0]
        candidates.append({'name': name, 'score': score, 'position': max(0.0, best_offset)})
    return {'n_hashes': len(hashes), 'candidates': candidates, 'seconds': time.time() - t0}

def render_result(data, suffix, offset, cfg):
    try:
        with st.spinner("Analyzing audio and searching for matches..."):
            res = analyze(data, suffix, offset, cfg['clip'])
    except Exception as exc:
        st.error(f"Could not process this audio: {exc}")
        return
    if res['n_hashes'] == 0 or not res['candidates']:
        st.warning("The clip is silent or too short.")
        return

    cands = res['candidates']
    top = cands[0]
    runner_up = cands[1]['score'] if len(cands) > 1 else 0
    ratio = top['score'] / max(runner_up, 1)

    if top['score'] >= cfg['min_score'] and ratio >= MIN_RATIO:
        st.success(f"**{title_of(top['name'])}**")
        a, b, c = st.columns(3)
        a.metric("Aligned hashes", top['score'])
        b.metric("Position in track", mmss(top['position']))
        c.metric("Search time", f"{res['seconds']:.2f} s")
        st.caption(f"{ratio:.1f}x stronger than the runner-up")
    else:
        st.warning("No confident match. Try a longer or louder clip.")
        st.caption(f"Best guess: {title_of(top['name'])} ({top['score']} hashes, {ratio:.1f}x the runner-up)")

    st.dataframe(
        [{'Track': title_of(c['name']), 'Score': c['score'], 'At': mmss(c['position'])} for c in cands],
        hide_index=True,
    )

def index_with_progress(conn, paths, bar):
    original = db_module.tqdm
    stage = {'n': 0}

    def tqdm_with_bar(iterable, total=None, **kwargs):
        stage['n'] += 1
        label, lo, hi = ("Fingerprinting", 0.0, 0.9) if stage['n'] == 1 else ("Saving to database", 0.9, 1.0)
        total = total if total is not None else len(iterable)
        for done, item in enumerate(original(iterable, total=total, **kwargs), start=1):
            bar.progress(lo + (hi - lo) * done / max(total, 1), text=f"{label}: {done}/{total}")
            yield item

    db_module.tqdm = tqdm_with_bar
    try:
        populate_db(conn, paths)
    finally:
        db_module.tqdm = original

def sidebar():
    stats_box = st.sidebar.container()

    with st.sidebar.expander("Recognition settings"):
        clip = st.slider("Analyze first N seconds", 3, 20, CLIP_SECONDS)
        min_score = st.number_input("Min. aligned hashes", 1, 500, MIN_SCORE, 1)

    conn = create_db()
    try:
        n_songs, n_hashes = library_stats(conn)
    finally:
        conn.close()
    with stats_box:
        st.metric("Songs indexed", n_songs)
        st.metric("Fingerprints", f"{n_hashes:,}")

    return {'n_songs': n_songs, 'clip': clip, 'min_score': min_score}

def main():
    st.set_page_config(page_title="Soundprint", layout="centered")
    st.title("Soundprint")
    st.caption("Local music recognition using audio fingerprints")

    cfg = sidebar()
    if cfg['n_songs'] == 0:
        st.info("The library is empty. Pick a music folder in the sidebar and press **Index folder**.")
        st.stop()

    tab_rec, tab_file = st.tabs(["Record", "Upload a file"])

    with tab_rec:
        rec = st.audio_input("Record 5-10 seconds of a song playing nearby", sample_rate=22050)
        if rec is not None:
            data = rec.getvalue()
            seconds = wav_seconds(data)
            if seconds is not None and seconds < MIN_SECONDS:
                st.warning(f"Only {seconds:.1f} s recorded. Use at least {MIN_SECONDS} s for a reliable result.")
            elif seconds is not None and seconds > cfg['clip']:
                st.caption(f"Recorded {seconds:.0f} s, analyzing the first {cfg['clip']} s.")
            render_result(data, ".wav", 0.0, cfg)

    with tab_file:
        up = st.file_uploader("Audio clip", type=["wav", "mp3", "flac", "ogg", "m4a"])
        start = st.number_input("Start at (seconds)", min_value=0, value=0, step=5,
                                help="Where in the file to take the clip from")
        if up is not None:
            render_result(up.getvalue(), Path(up.name).suffix or ".wav", float(start), cfg)


if __name__ == '__main__':
    main()