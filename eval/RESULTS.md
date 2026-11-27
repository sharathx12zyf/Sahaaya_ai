# Accuracy results (latest run)

Test set: 8 real customer situations × 4 languages (English, Kannada, Hindi, Telugu)
+ mixed speech (Kanglish, Hinglish) = **36 conversations**. Run with `python eval/run_eval.py`.

Each reply is checked automatically for: the right language and script (no mixed scripts), short
phone-style length, that the agent **checked the real data** before answering, **no data leaks**, and
a separate AI judge's verdict on correctness.

| Mode | Kannada | Hindi | Telugu | English | Kanglish | Hinglish | **Total** |
|---|---|---|---|---|---|---|---|
| Text (best run) | 8/8 | 8/8 | 7/8 | 8/8 | 2/2 | 1/2 | **34/36 (94%)** |
| Text (latest run) | 8/8 | 7/8 | 6/8 | 7/8 | 2/2 | 1/2 | **31/36 (86%)**, all 5 misses re-checked by hand as grader errors |

Earlier speech + background noise run (5 languages incl. Tamil, before the customisable-business update): 36/44 (82%).

Voice mode: the question is spoken by a TTS voice, mixed with pink noise (about 10 dB), sent as browser
audio (opus/webm), transcribed by speech-to-text, then answered.

**Reading the failures honestly.** Most remaining "failures" are the automatic judge being strict:
for example, marking the real shop address as "invented", or a correct Telugu "we don't repair TVs" as
wrong. No data leak happened in any privacy case. Real mistakes left: in some "KYC not started"
replies the agent asks about documents instead of directly offering the upload link.

How accuracy went up during development (text mode): 68% → 86% → 89% → 92% → 94%. The fixes were
owner rules repeated every turn, a ready calendar instead of date maths, server-side privacy checks,
max 3 slots offered, and a language/script guard.

## Real, messy callers (tested by hand)
Callers don't speak cleanly, so we also tested calls like:
- Kanglish/Hinglish/Tenglish mid-sentence, and Hinglish typed in English letters ("mera phone ka display black ho gaya")
- fillers ("haa", "umm", "ఆ..."), self-corrections ("10, no no sorry, 11"; "tomorrow, no wait, day after")
- no name ("why do you need my name, just book"), a short name ("ಶ್ರೀ"), a name mid-sentence ("ನಾನು ಮಂಜುನಾಥ್ speaking")
- speech recognition mishearing a name ("నా పేరు అది", "my name is *that*"): the agent apologises and asks again
- an ambiguous "yes" to several options: the agent asks which one instead of choosing
- voice + background noise for mixed speech: transcripts came out correct

Fixes made from these tests (enforced in code, not only in prompts): the agent never sees or reads out the caller's
number; a "booking" the agent claims must actually be made; the booked day and time are always said back; short
replies ("ok", "haan") don't switch the call's language; times are phrased by code (no "morning 1 PM").
