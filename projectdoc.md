🧾 Product Requirements Doc — Chronos Inbound
💡 Product Overview
Chronos Inbound is a 24/7 AI voice receptionist that answers phone calls in real time, converses naturally with callers, checks availability, and books appointments via Cal.com. After each call, it logs the data to Supabase, and sends a daily summary email report.

The entire flow is voice-first, fully automated, and optimized for low-latency interaction using AssemblyAI’s Universal-Streaming API and Deepgram TTS.

🧠 Core Use Case
“A customer calls your business number. Chronos answers, handles the entire conversation, books the slot, and sends you a digest of all bookings that day — no human ever touches it.”

🛠️ Tech Stack
Layer	Tool
Telephony	Twilio Voice + Media Streams
Transcription	AssemblyAI Universal-Streaming
TTS	Deepgram
Backend	FastAPI
Data Store	Supabase
Calendar Sync	Cal.com API
Email Delivery	Gmail SMTP / Resend
Frontend (Optional)	Next.js (admin dashboard)

🧭 System Flow
🔁 Step-by-Step Flow
Inbound Call → Twilio
User calls your Twilio number → webhook hits FastAPI → TwiML responds with Stream block → audio routed to WebSocket

Real-Time Conversation (AssemblyAI + GPT + Deepgram)

Transcribes caller input in real-time

Uses GPT to:

Parse intent (e.g., "I'd like to book a call")

Offer Cal.com slots

Handle fallback/retries/reschedule

Deepgram TTS sends bot response back to Twilio

Booking

Once user confirms a time, FastAPI calls Cal.com /v1/bookings

Booking is created and confirmed live to user

Logging

All relevant data:

Phone number

Transcript

Booking time

Call timestamp

Logged to Supabase in calls table

Daily Digest

At 10PM IST, a scheduled job runs:

Fetches all calls from that day

Formats summary

Sends email to admin

📦 Key Features
📞 Real-time call handling (under 300ms latency)

🗓️ Smart slot handling using Cal.com’s real-time availability

🤖 Natural dialogue via GPT parsing + fallback logic

🧠 Multi-turn memory — understands past responses in-session

📨 Automated daily digest email

🔐 Legal & opt-in safe (inbound-only, disclaimer included)

📊 Data Schema (Supabase)
Table: calls

Field	Type	Notes
id	UUID	Primary key
phone_number	TEXT	Caller ID
transcript	TEXT	Full conversation
booking_time	TIMESTAMP	Time confirmed via Cal.com
created_at	TIMESTAMP	Call received time
status	TEXT	booked, incomplete, etc.