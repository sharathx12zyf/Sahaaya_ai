# Accuracy results (latest run)

Test set: 8 real customer situations × 5 languages (Kannada, Hindi, Telugu, Tamil, English)
+ mixed speech (Kanglish, Hinglish) = **44 conversations**. Run with `python eval/run_eval.py`.

Each reply is checked automatically for: the right language and script (no mixed scripts), short
phone-style length, that the agent **checked the real data** before answering, **no data leaks**, and
a separate AI judge's verdict on correctness.

| Mode | Kannada | Hindi | Telugu | Tamil | English | Kanglish | Hinglish | **Total** |
|---|---|---|---|---|---|---|---|---|
| Text | 8/8 | 8/8 | 6/8 | 8/8 | 7/8 | 2/2 | 0/2 | **39/44 (89%)** |
| Voice + background noise | 7/8 | 6/8 | 6/8 | 7/8 | 6/8 | 2/2 | 2/2 | **36/44 (82%)** |

Voice mode: the question is spoken by a TTS voice, mixed with pink noise (about 10 dB), sent as browser
audio (opus/webm), transcribed by speech-to-text, then answered.

**Reading the failures honestly.** Most remaining "failures" are the automatic judge being strict:
for example, marking the real shop address as "invented", or a correct Telugu "we don't repair TVs" as
wrong. No data leak happened in any privacy case. Real mistakes left: in some "KYC not started"
replies the agent asks about documents instead of directly offering the upload link.

How accuracy went up during development (same test set, text mode): 68% → 86% → 89%. The fixes were
owner rules repeated every turn, a ready calendar instead of date maths, server-side privacy checks,
max 3 slots offered, and a language/script guard.
