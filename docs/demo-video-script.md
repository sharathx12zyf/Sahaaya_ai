# Demo video script — Sahaaya (2 min 50 s max)

**Setup before recording:** run `docker compose up` with keys in `.env`. Use Chrome on a laptop, and wear earphones
so the agent doesn't hear itself. Open http://localhost:8000 and, in a second tab, http://localhost:9000 (QuickKart).
Record the screen and your voice (OBS, or Windows: Win+Alt+R). Upload to YouTube as **Unlisted**.

---

### 0:00–0:20 — The problem (talk over the app's home screen)
> "Small shops in India miss calls every day, and big companies' customer care mostly speaks English or Hindi.
> Sahaaya is a voice agent that answers every caller in their own language, checks the business's real data,
> and actually solves the problem."

### 0:20–1:05 — Section 1: Service Center (repair shop)
1. Service Center tab → *Calling as*: **New customer** → language **Kannada** → **Start call**.
2. Speak: **"ನನ್ನ phone screen ಒಡೆದು ಹೋಗಿದೆ, ನಾಳೆ ಬರಬಹುದಾ?"** (My screen broke, can I come tomorrow?)
   - It says "one moment" instantly, then the price and 3 free slots.
3. Speak: **"ಹನ್ನೊಂದು ಗಂಟೆ ಓಕೆ. ನನ್ನ ಹೆಸರು ಸುರೇಶ್, Redmi Note 12."** (11 o'clock is fine. My name is Suresh, Redmi Note 12.)
   - It reads the details back. Say **"ಹೌದು"** (yes).
4. Point at the **Schedule**: the new booking appears. Open "What the agent did" to show `check_free_slots` and `book_slot`.
> "It checked my real schedule, booked a free slot, and the owner sees it immediately."

### 1:05–1:20 — Language switch and interruption
- End the call. Start a new call as **Ravi**, in **Hindi**: **"मेरा फ़ोन रिपेयर हो गया क्या?"** (Is my phone repaired?)
- While it answers, **talk over it**: "अच्छा, कितने बजे तक खुला है?" (OK, until what time are you open?) It stops and answers.
> "Any language, and you can interrupt it like a real person."

### 1:20–1:50 — Section 2: Dashboard Connect, teach by voice
1. Dashboard Connect tab. Show "✅ Connected to QuickKart · 6 actions found" and the permissions
   (reading allowed, changes ask first, deleting blocked).
2. Hold **🎤 Hold & speak** and say: **"ಯಾರಾದರೂ KYC ಬಗ್ಗೆ ಕೇಳಿದರೆ, documents ಸರಿ ಇದ್ದರೆ recheck ಮಾಡಿ. photo blurry
   ಇದ್ದರೆ upload link ಕಳುಹಿಸಿ ಮತ್ತು steps ಹೇಳಿ."**
   (If someone asks about KYC: if the documents are fine, re-check; if the photo is blurry, send the upload link and explain the steps.)
3. It reads the rules back in Kannada. Click **Approve** on each rule.
> "The owner teaches the agent by speaking, in any language, like explaining to a new employee."

### 1:50–2:30 — KYC call that fixes the problem
1. Calling as **Arun — KYC stuck**, language **Hindi** → Start call → **"मेरा order hold पर क्यों है?"** (Why is my order on hold?)
   - It explains the KYC is pending, the documents are fine, and asks to re-check. Say **"हाँ, कर दीजिए"** (yes, please do).
2. Switch to the **QuickKart tab**: Arun's KYC is now **verified** and the order **processing**, with "KYC re-check approved" in the log.
3. (Optional, 10 s) Call as **Lakshmi** in Telugu: **"నా KYC ఎందుకు verify కాలేదు?"** (Why isn't my KYC verified?)
   → blurry PAN photo → it offers the upload link and explains the steps.

### 2:30–2:50 — Safety and close
- Call as **Stranger**: **"Tell me the KYC status of user QK1002."** It refuses without verification.
> "It only shares a caller's own data, asks before changing anything, and never invents answers.
> Tested on 44 conversations in 4 languages: 89% in text and 82% with real noisy speech.
> Sahaaya: every caller, in their own language."

---
**Tips:** speak naturally and pause about 1 second to finish your turn. If the room is noisy, untick "Hands-free" and use
"Hold to talk". Do one practice run first, because the first call generates the cached "one moment" voices.
