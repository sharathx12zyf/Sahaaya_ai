# Demo video script — Sahaaya AI (3 minutes max)

**Before recording:** run `docker compose up` with keys in `.env`. Open Chrome at http://localhost:8000 and, in a 2nd tab,
http://localhost:9000 (the company dashboard). Wear earphones. Do one practice run first, because it prepares the
"one moment" voices. In the Service Center tab, click **Start over** so setup begins clean. Record screen + voice, then
upload to YouTube as **Unlisted**.

---

## Part 1 — Set up the agent by talking (0:00–0:50)
> "Sahaaya is a voice agent for any business. I just tell it what I need, in my language."

Service Center tab → **Hold & speak** (or type) to the setup assistant:
> "I run a mobile phone repair shop called *[your shop name]* in *[area]*. Whenever a call comes, talk like a normal person,
> don't say you are AI at the start. Give 1-hour slots and be available 24/7. Book slots for customers and update my
> dashboard with their name, mobile number and problem. If they ask about money, tell them we need to check the phone,
> please visit once, after that we will give a quotation. Agent name Priya."

- It saves everything and **asks a follow-up question**. Answer it (e.g. "that's all").
- It says **"press Demo call"**. Show the switches: **Agent active**, and "Say AI assistant" turned **off**.
- (Optional) Say a change, e.g. *"Also tell them we are near the bus stand."* It updates.

## Part 2 — Testing: a customer calls (0:50–1:45)
> "Setup is done. Now my friend calls as a customer."

Click **📞 Demo call**. Your friend speaks, for example in Kannada:
1. *"ನಮಸ್ಕಾರ, ನನ್ನ phone ಬಿದ್ದು screen ಒಡೆದಿದೆ, touch ಕೆಲಸ ಮಾಡ್ತಿಲ್ಲ"* (Hello, my phone fell, the screen broke and touch isn't working)
   → Priya offers 3 times.
2. *"ಎಷ್ಟು ಖರ್ಚಾಗುತ್ತೆ?"* (How much will it cost?)
   → "We need to check the phone first, please visit once; then we give a quotation."
3. *"ಇವತ್ತು ರಾತ್ರಿ 9 ಗಂಟೆಗೆ ಬರಬಹುದಾ? ನನ್ನ ಹೆಸರು ಕಿರಣ್, phone Vivo V27"* (Can I come tonight at 9? My name is Kiran, the phone is a Vivo V27)
   → it checks 9 PM and reads the details back.
4. *"ಹೌದು"* (Yes) → booked.
5. Point at the dashboard: **📋 Bookings** shows **name, mobile, problem and time**, the schedule highlights the slot, and
   a notification appears.
6. (Optional) *"ನೀವು ಮನುಷ್ಯರಾ?"* (Are you a human?) → it answers honestly, which shows it's trustworthy.

> "Every call is answered 24/7, in the customer's language, and lands on my dashboard."

## Part 3 — Dashboard Connect: set up (1:45–2:20)
> "Bigger companies already have a dashboard. Sahaaya plugs into it."

Dashboard Connect tab:
1. Show **"Connected to QuickKart · 6 actions found"** (your company dashboard on port 9000) and the permissions:
   reading allowed, changes ask the caller first, delete blocked.
2. **Teach by voice** (any language), e.g. *"ಯಾರಾದರೂ KYC ಬಗ್ಗೆ ಕೇಳಿದರೆ, documents ಸರಿ ಇದ್ದರೆ recheck ಮಾಡಿ. photo blurry ಇದ್ದರೆ
   upload link ಕಳುಹಿಸಿ ಮತ್ತು steps ಹೇಳಿ."* (If someone asks about KYC: if the documents are fine, re-check; if the photo
   is blurry, send the upload link and explain the steps.) → it reads the rules back → **Approve**.

## Part 4 — Testing: KYC call fixed on the dashboard (2:20–2:55)
Calling as **Arun — KYC stuck**, language Hindi → **Start call**:
- *"मेरा order hold पर क्यों है? KYC भी pending है"* (Why is my order on hold? KYC is also pending)
  → "your documents are fine, it's stuck; shall I re-check?" → *"हाँ"* (yes)
- Switch to the QuickKart tab: **KYC verified, order processing**, and "KYC re-check approved" in the log.
- (Optional) Calling as **Lakshmi** in Telugu: *"నా KYC ఎందుకు verify కాలేదు?"* (Why isn't my KYC verified?)
  → blurry PAN photo → it sends the upload link with steps.

> "Any business, any language, by voice. That's Sahaaya AI."

---
**Tips:** speak naturally and pause about 1 second to finish your turn. In a noisy room, untick "Hands-free" and use
"Hold to talk". If something goes wrong, end the call and start again: each call is independent.
