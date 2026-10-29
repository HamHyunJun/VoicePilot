import numpy as np

from voicepilot.audio import SegmenterConfig, SpeechSegmenter

SR = 16000


def _noise(seconds, level=0.002, seed=0):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(SR * seconds)) * level).astype(np.float32)


def _tone(seconds, amp=0.2):
    t = np.arange(int(SR * seconds)) / SR
    return (np.sin(2 * np.pi * 220 * t) * amp).astype(np.float32)


def _feed_in_blocks(seg, audio, block=480):
    out = []
    for i in range(0, len(audio), block):
        out.extend(seg.feed(audio[i : i + block]))
    return out


def test_detects_one_utterance_between_silence():
    seg = SpeechSegmenter()
    audio = np.concatenate([_noise(1.0), _tone(1.0), _noise(1.0, seed=1)])
    segments = _feed_in_blocks(seg, audio)
    assert len(segments) == 1
    # 말소리 1초 + 앞쪽 여유(pre-roll) + 끝 침묵 일부
    assert 1.0 <= len(segments[0]) / SR <= 2.1


def test_ignores_short_clicks():
    seg = SpeechSegmenter()
    audio = np.concatenate([_noise(0.5), _tone(0.06), _noise(1.0, seed=2)])
    assert _feed_in_blocks(seg, audio) == []


def test_splits_two_utterances():
    seg = SpeechSegmenter()
    audio = np.concatenate([_noise(0.5), _tone(0.6), _noise(1.0, seed=3), _tone(0.6), _noise(1.0, seed=4)])
    assert len(_feed_in_blocks(seg, audio)) == 2


def test_long_speech_is_cut_at_max_length():
    seg = SpeechSegmenter(SegmenterConfig(max_speech_s=1.0))
    segments = _feed_in_blocks(seg, np.concatenate([_noise(0.3), _tone(2.5)]))
    assert len(segments) == 2
    assert all(len(s) / SR <= 1.05 for s in segments)


def test_flush_returns_ongoing_speech():
    seg = SpeechSegmenter()
    _feed_in_blocks(seg, np.concatenate([_noise(0.3), _tone(0.5)]))
    assert seg.in_speech
    assert seg.flush() is not None
