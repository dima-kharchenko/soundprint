import os
import librosa
import librosa.display
import numpy as np
import matplotlib.pyplot as plt
import sounddevice as sd

from scipy.ndimage import maximum_filter
from collections import Counter
from scipy.io.wavfile import write


def mmss(seconds):
    seconds = round(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"

def get_paths(root):
    paths = []
    for path, _, files in os.walk(root):
        for name in files:
            if name.lower().endswith(('.mp3', '.wav', '.flac', '.ogg')):
                paths.append(os.path.join(path, name))

    return paths

def process_song(path, n_fft=2048, duration=None, offset=0, n_neighbours=10):
    D, sr = get_spectrogram(path=path, n_fft=n_fft, duration=duration, offset=offset)
    points = get_points(D, sr, n_fft)
    hashes = get_hashes(points, n_neighbors=n_neighbours)

    return hashes

def get_spectrogram(path, n_fft=2048, duration=None, offset=0):
    y, sr = librosa.load(path, sr=22050, duration=duration, offset=offset)
    D = librosa.amplitude_to_db(np.abs(librosa.stft(y, n_fft=n_fft)), ref=np.max)

    return D, sr

def get_points(D, sr, n_fft=2048):
    local_max = maximum_filter(D, size=(30, 30)) == D 
    peaks = local_max & (D > -30)

    freq_idx, time_idx = np.where(peaks)
    times = librosa.frames_to_time(time_idx, sr=sr)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)[freq_idx]

    points = sorted(zip(times, freqs)) 

    return points

def make_hash(f1, f2, dt):
    f1, f2 = int(f1), int(f2)
    dt = int(dt * 10)
    return (f1 << 24) | (f2 << 10) | dt 


def get_hashes(points, n_neighbors=10):
    hashes = []
    for i, (t1, f1) in enumerate(points):
        for t2, f2 in points[i+1:i+n_neighbors]:
            h = make_hash(f1, f2, t2-t1)
            hashes.append((h, t1)) 

    return hashes

def get_matches(conn, h_snippet):
    cursor = conn.cursor()
    matches = {}

    for h, t1 in h_snippet:
        cursor.execute("""
            SELECT songs.name, fingerprints.offset
            FROM fingerprints
            JOIN songs ON songs.id = fingerprints.song_id
            WHERE fingerprints.hash = ?
        """, (h,))

        for name, t2 in cursor.fetchall():
            offset = round(t2-t1, 1)
            matches.setdefault(name, []).append(offset)

    return matches

def best_matches(matches, n=5):
    scores = [] 
    for name, offsets in matches.items():
        score = Counter(offsets).most_common(1)[0][1]
        scores.append((score, name))

    return sorted(scores, reverse=True)[:n]

def record_snippet(device, duration, sr, filename='snippet.wav'):
    sr_native = sd.query_devices(device=device)['default_samplerate']

    recording = sd.rec(int(duration * sr_native), samplerate=sr_native, channels=1, device=device)
    sd.wait()
    y = recording.flatten()
    y_resampled = librosa.resample(y, orig_sr=sr_native, target_sr=22050)
    write(filename, sr, y_resampled)

def plot_song(path, n_fft=2048, duration=None, offset=0):
    D, sr = get_spectrogram(path=path, n_fft=n_fft, duration=duration, offset=offset)

    points = get_points(D, sr, n_fft)
    times, freqs = zip(*points)

    librosa.display.specshow(D, sr=sr, x_axis='time', y_axis='linear')
    plt.scatter(times, freqs, color='cyan', s=10)
    plt.colorbar(format='%+2.0f dB')
    plt.tight_layout()
    plt.show()