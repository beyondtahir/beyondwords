# Audiobook Production — Guidance-Only Workflow

Beyondwords provides **no audiobook automation**. This file is a checklist and
requirements reference for producing one manually or with external tools.

## Contents
1. ACX/Audible technical requirements
2. Production checklist
3. AI narration options
4. Cost reality

## 1. ACX/Audible technical requirements

Per-file requirements (ACX Audio Submission Requirements):
- **Format**: MP3, 192 kbps or higher, **CBR** (constant bit rate), 44.1 kHz, mono or stereo (consistent across all files).
- **Loudness**: RMS between **−23 dB and −18 dB**; true peak ≤ **−3 dB**; noise floor ≤ **−60 dB**.
- **Room tone**: 0.5–1 second at the start of each file; 1–5 seconds at the end.
- **One chapter per file**; each file ≤ 120 minutes; opening and closing credits files required ("This is [title], written by…, narrated by…").
- No explicit/illegal content flags; consistent narrator voice across the book.
- Retail sample: 1–5 minutes from the main body (not the intro/credits).

## 2. Production checklist

- [ ] Final manuscript locked (record from the *published* text — audio must match)
- [ ] Record or generate chapter-by-chapter MP3s (one file per chapter)
- [ ] Master every file: RMS −23…−18 dB, peaks ≤ −3 dB, noise floor ≤ −60 dB (check with a loudness meter, e.g., Audacity's or ffmpeg's loudnorm analysis)
- [ ] Add room tone head/tail per file
- [ ] Opening credits + closing credits files
- [ ] Retail sample cut
- [ ] Audiobook cover: **2400 × 2400 px square** JPG (not the ebook cover's 1.6:1)
- [ ] Upload to ACX (guided manual flow) → review takes ~10–20 business days

## 3. AI narration options

- **KDP "Audiobooks with virtual voice" (beta)** — Amazon's own AI narration, built into KDP; free; English; eligible titles only; audio is editable in the Virtual Voice Studio. Check the KDP help pages for current eligibility — it's a beta and rules change.
- **External AI narration tools** (ElevenLabs-class services) — produce compliant MP3s externally, then upload to ACX manually. These are third-party, paid, and outside this suite; verify ACX's current AI-narration policy before using them.
- **Disclosure**: ACX/KDP may require AI-narration disclosure; answer honestly, as with text/images.

## 4. Cost reality

Human narration via ACX royalty-share costs nothing upfront but halves royalties; per-finished-hour production runs $100–400+/PFH (a 50k-word book ≈ 5–6 finished hours). Virtual Voice is free while in beta. Never promise audiobook income.
