"""Voice quality: tester ratings, optional automatic MOS score, and audio issues from the logs.

Optional MOS (off by default, settings "mos_enabled"):
  DNSMOS by Microsoft (https://github.com/microsoft/DNS-Challenge, DNSMOS folder).
  Code: MIT. Model file: CC-BY-4.0 (attribution: "DNSMOS P.835, Microsoft").
  Runs locally on CPU with onnxruntime; nothing is uploaded.
  It rates signal quality (SIG), background noise (BAK) and overall (OVRL), 1-5.
  It measures how clean the audio is, NOT how natural the voice sounds.
  Setup:  pip install -e "report_module[mos]"
          python -m report_module.voice_quality --download
"""

import difflib
import hashlib
import sys
import urllib.request
import wave
from pathlib import Path

from report_module.schema import AudioIssue, CallData, MosScore, Ratings, VoiceQualitySection
from report_module.textutil import fmt_time, normalize, short

RATING_KEYS = ("naturalness", "clarity", "pronunciation", "accent_fit", "politeness")

MODEL_URL = "https://raw.githubusercontent.com/microsoft/DNS-Challenge/master/DNSMOS/DNSMOS/sig_bak_ovr.onnx"
MODEL_SHA256 = "269fbebdb513aa23cddfbb593542ecc540284a91849ac50516870e1ac78f6edd"
MODEL_PATH = Path.home() / ".cache" / "report_module" / "sig_bak_ovr.onnx"

# From dnsmos_local.py (non-personalized model): raw network output -> MOS.
_POLY_SIG = (-0.08397278, 1.22083953, 0.0052439)
_POLY_BAK = (-0.13166888, 1.60915514, -0.39604546)
_POLY_OVR = (-0.06766283, 1.11546468, 0.04602535)
_FS = 16000
_INPUT_SECONDS = 9.01


# ---------------------------------------------------------------------------
# DNSMOS
# ---------------------------------------------------------------------------


def download_model(path: Path = MODEL_PATH) -> Path:
    """Download the DNSMOS model (1.1 MB) and check its SHA-256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = urllib.request.urlopen(MODEL_URL, timeout=60).read()
    if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
        raise RuntimeError("Downloaded DNSMOS model does not match the expected checksum.")
    path.write_bytes(data)
    return path


def _read_wav_mono_16k(path: str):
    """Read a 16-bit PCM WAV as float32 mono at 16 kHz (simple resampling if needed)."""
    import numpy as np

    with wave.open(path, "rb") as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError("Only 16-bit PCM WAV recordings are supported.")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != _FS:  # e.g. 8 kHz phone mode -> 16 kHz by linear interpolation
        n_out = int(len(audio) * _FS / rate)
        audio = np.interp(np.linspace(0, len(audio) - 1, n_out), np.arange(len(audio)), audio).astype(np.float32)
    return audio


def dnsmos_score(wav_path: str, model_path: Path = MODEL_PATH) -> MosScore:
    """Average DNSMOS over 9-second windows, exactly like Microsoft's dnsmos_local.py."""
    import numpy as np
    import onnxruntime as ort

    audio = _read_wav_mono_16k(wav_path)
    if len(audio) == 0:
        raise ValueError("Recording is empty.")
    seg_len = int(_INPUT_SECONDS * _FS)
    while len(audio) < seg_len:  # short clips are repeated to fill one window
        audio = np.append(audio, audio)
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    sig, bak, ovr = [], [], []
    hops = int(np.floor(len(audio) / _FS) - _INPUT_SECONDS) + 1
    for i in range(hops):
        seg = audio[int(i * _FS): int((i + _INPUT_SECONDS) * _FS)]
        if len(seg) < seg_len:
            continue
        raw_sig, raw_bak, raw_ovr = session.run(None, {"input_1": seg[np.newaxis, :].astype("float32")})[0][0]
        sig.append(np.polyval(_POLY_SIG, raw_sig))
        bak.append(np.polyval(_POLY_BAK, raw_bak))
        ovr.append(np.polyval(_POLY_OVR, raw_ovr))
    return MosScore(model="DNSMOS P.835 (Microsoft, CC-BY-4.0)", sig=round(float(np.mean(sig)), 2),
                    bak=round(float(np.mean(bak)), 2), ovrl=round(float(np.mean(ovr)), 2))


def try_mos(data: CallData, settings: dict) -> tuple[MosScore | None, str]:
    if not settings.get("mos_enabled"):
        return None, "off"
    if not data.recording_path or not Path(data.recording_path).exists():
        return None, "no recording for this call"
    if not MODEL_PATH.exists():
        return None, "model not downloaded (run: python -m report_module.voice_quality --download)"
    try:
        return dnsmos_score(data.recording_path), "ok"
    except ImportError:
        return None, 'not installed (run: pip install -e "report_module[mos]")'
    except Exception as e:  # never break the report because of the optional scorer
        return None, f"error: {e}"


# ---------------------------------------------------------------------------
# Audio issues from logs
# ---------------------------------------------------------------------------


def _sentences(text: str) -> list[str]:
    import regex

    return [s for s in (normalize(p) for p in regex.split(r"[.?!।॥]+", text)) if len(s.split()) >= 4]


def find_audio_issues(data: CallData, settings: dict) -> list[AudioIssue]:
    issues: list[AudioIssue] = []
    limit = settings["audio_issues"]["long_silence_ms"]
    callers = [u for u in data.transcript if u.role == "caller"]

    # Long silence: the caller waited too long for the reply.
    for t in data.turns:
        if t.turn_index > 0 and t.total_ms and t.total_ms > limit:
            offset = callers[t.turn_index - 1].offset_s if t.turn_index - 1 < len(callers) else None
            issues.append(AudioIssue(kind="long_silence", offset_s=offset, time=fmt_time(offset),
                                     detail=f"Turn {t.turn_index}: {t.total_ms / 1000:.1f} s of silence before the agent replied."))

    agents = [u for u in data.transcript if u.role == "agent"]
    # Talking over: agent speech cut off by the caller (barge-in).
    for u in agents:
        if u.interrupted:
            issues.append(AudioIssue(kind="talk_over", offset_s=u.offset_s, time=fmt_time(u.offset_s),
                                     detail=f"Caller and agent spoke at the same time; agent stopped at: \"{short(u.text, 70)}\""))
    logged = sum(1 for i in issues if i.kind == "talk_over")
    if data.interruptions > logged:
        issues.append(AudioIssue(kind="talk_over", detail=f"{data.interruptions - logged} more overlap(s) counted by the tester."))

    # Cut-off: a reply that ends mid-sentence without being interrupted.
    for u in agents:
        text = u.text.strip()
        if not u.interrupted and len(text) > 20 and text[-1] not in ".?!।॥…\"'":
            issues.append(AudioIssue(kind="cut_off", offset_s=u.offset_s, time=fmt_time(u.offset_s),
                                     detail=f"Reply may be cut off: \"…{text[-60:]}\""))

    # Repeated phrases: the same sentence (or nearly) in 3+ agent turns, or the exact same
    # whole reply twice in a row. (Re-asking once in new words after an error is fine.)
    seen: list[tuple[str, list[float]]] = []
    flagged: set[str] = set()
    previous_reply = None
    for u in agents:
        reply = normalize(u.text)
        if reply and reply == previous_reply and reply not in flagged:
            flagged.add(reply)
            issues.append(AudioIssue(kind="repeated_phrase", offset_s=u.offset_s, time=fmt_time(u.offset_s),
                                     detail=f"Agent said the same reply twice in a row: \"{short(u.text, 80)}\""))
        previous_reply = reply
        for s in set(_sentences(u.text)):
            match = next((group for group in seen if difflib.SequenceMatcher(None, group[0], s).ratio() >= 0.9), None)
            if match is None:
                seen.append((s, [u.offset_s]))
                continue
            match[1].append(u.offset_s)
            if len(match[1]) >= 3 and match[0] not in flagged:
                flagged.add(match[0])
                issues.append(AudioIssue(kind="repeated_phrase", offset_s=u.offset_s, time=fmt_time(u.offset_s),
                                         detail=f"Agent repeated: \"{short(match[0], 80)}\" ({len(match[1])} times)"))
    issues.sort(key=lambda i: (i.offset_s is None, i.offset_s or 0))
    return issues


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------


def analyse_voice_quality(data: CallData, ratings: Ratings, settings: dict) -> VoiceQualitySection:
    given = [getattr(ratings, k) for k in RATING_KEYS if getattr(ratings, k) is not None]
    mos, status = try_mos(data, settings)
    return VoiceQualitySection(
        ratings=ratings,
        rating_average=round(sum(given) / len(given), 2) if given else None,
        mos=mos,
        mos_status=status,
        issues=find_audio_issues(data, settings),
    )


def voice_quality_score(vq: VoiceQualitySection) -> float | None:
    """0-100: tester ratings (70%) and MOS (30%), minus 5 per audio issue (max -20)."""
    parts = []
    if vq.rating_average is not None:
        parts.append((0.7, (vq.rating_average - 1) / 4))
    if vq.mos is not None:
        parts.append((0.3, (vq.mos.ovrl - 1) / 4))
    if not parts:
        return None
    base = 100 * sum(w * v for w, v in parts) / sum(w for w, _ in parts)
    return round(max(0.0, base - min(20, 5 * len(vq.issues))), 1)


if __name__ == "__main__":
    if "--download" in sys.argv:
        print(f"Saved DNSMOS model to {download_model()}")
    elif len(sys.argv) == 2:
        print(dnsmos_score(sys.argv[1]))
    else:
        print("Usage: python -m report_module.voice_quality --download | <file.wav>")
