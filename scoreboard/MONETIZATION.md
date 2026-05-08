# Scoreboard System — Monetization & Sponsorship Guide

Everything in this system that can carry a sponsor, run an ad, or generate revenue from a broadcast partner. Use this as a sales reference when pitching packages to sponsors.

---

## Quick Summary

| Placement | Format | When Visible | Exclusivity |
|---|---|---|---|
| Sponsor Strip | Logo + tier label | Always (broadcast) | Multi-tier |
| Corner Bug | Logo | Always (broadcast) | 1 sponsor |
| Ad Slots A / B / C | Image or Video | Always (broadcast) | 3 sponsors |
| Scoring Sponsor | Logo | Every try / goal | 1 sponsor |
| L-Card | PNG / GIF / Video | During live video | 1 sponsor |
| Video Ad Overlay | Image / Video | Operator-triggered | 1 per slot |
| Ad Scheduler | Image / Video / Text | Break-time playback | Unlimited slots |
| Reaction Wall Sponsor | Logo | While wall is live | 1 sponsor |
| Selfie Wall Sponsor | Logo | Every selfie reveal | 1 sponsor |
| Poll / QR Campaign | Custom URL + headline | Operator-triggered | 1 per activation |
| Announcement Logo | Logo | With announcements | Per-announcement |
| Papare / Production Credit | Logo + text | Always (sponsor bar) | 1 (yours) |

---

## 1. Static Display Sponsorships

These placements are always visible on the broadcast screen throughout the match with no manual intervention required after setup.

### 1.1 Sponsor Strip — Bottom Ticker

**Where:** Scrolling ticker bar along the bottom of the broadcast display.

**Tiers (configured in Dashboard → Sponsors):**

| Tier | Logo Size | Position | Limit |
|---|---|---|---|
| **Principal** ★ | Large, gold-tinted row | Featured above all others | **1 only** |
| **Official** | Medium logo | Main scrolling strip | Unlimited |
| **Partner** | Small logo | "Presented By" bar | Unlimited |

**State keys:** `S.sponsors[]` (array), `S.presentedByText` (label text, e.g. "PRESENTED BY")

**Setup:** Dashboard → Sponsors page. Upload a logo image for each sponsor and assign a tier. Changes apply to the broadcast display immediately.

**Sales angle:** Principal sponsor gets the largest, most prominent placement and is visually separated from all others. Sell as the "naming rights" equivalent for the match broadcast.

---

### 1.2 Corner Bug — Persistent Sponsor Logo

**Where:** One fixed corner of the broadcast screen at all times (top-left, top-right, bottom-left, or bottom-right — operator selects).

**Format:** Logo image (PNG with transparency recommended). Stays visible on screen during all match play.

**State keys:** `S.lBug.logo`, `S.lBug.position`, `S.lBug.visible`

**Setup:** Dashboard → Operator → Corner Bug section. Upload logo, pick corner, press Show.

**Sales angle:** Highest dwell time of any placement. The logo is on screen for the entire match duration with no interruptions. Ideal for title sponsor or key broadcast partner.

---

### 1.3 Ad Slots A / B / C — Lower-Third Banner

**Where:** Three side-by-side ad panels displayed below the main scoreboard on the broadcast display. All three run simultaneously.

**Format:** Image (JPG / PNG / GIF) or Video (MP4 / WebM). No file size limit — stored on server.

**State keys:** `S.adSlot1`, `S.adSlot2`, `S.adSlot3`

**Setup:** Dashboard → Ad Slots page. Upload content for each slot independently. Changes are live immediately.

**Sales angle:** Three independent sponsor placements always visible below the score. Sell as A / B / C packages — e.g. principal gets Slot A (largest / leftmost), official gets B, partner gets C.

---

## 2. Event-Triggered Sponsorships

These placements fire automatically when specific match events occur, reaching viewers at peak engagement moments.

### 2.1 Scoring / Celebration Sponsor

**Where:** Full-screen celebration overlay that fires every time a scoring event is recorded (try, conversion, penalty goal, penalty try, drop goal).

**Format:** Logo image shown in the lower portion of the full-screen celebration graphic.

**State key:** `S.celebSponsor`

**Setup:** Dashboard → Sponsors → Goal Sponsor section. Upload the logo once — it auto-fires on every score.

**Sales angle:** The most premium event-driven placement. Every score triggers a full-screen moment with the sponsor logo. In a rugby match with 10–20 scoring events, that's 10–20 guaranteed full-screen exposures at the highest emotional peaks of the match.

---

### 2.2 Player Intro Broadcast

**Where:** Full-screen player intro card pushed to the broadcast display. Shows player name, number, position, team, and a one-line stat.

**Format:** Sponsor logo can be included in the intro card design.

**State key:** `S.playerIntro`

**Setup:** Dashboard → Announce → Player Intro Broadcast.

**Sales angle:** Sponsor the pre-match player walk-on sequence or man-of-the-match reveal. Each player intro is a dedicated broadcast moment.

---

## 3. Video Feed Monetization

These placements only appear when the Video Source feature is active (the broadcast is showing a live video feed through the system).

### 3.1 L-Card — L-Shaped Video Overlay

**Where:** An L-shaped transparent graphic overlaid on the live video feed. The cut-out in the upper-right reveals the video beneath — sponsors occupy the left strip and bottom strip.

**Format:** 1920×1080 PNG with transparency, or animated GIF / MP4 video.
- Left strip: 576px wide × 1080px tall (30% of width)
- Bottom strip: 1920px wide × 302px tall (28% of height)
- Transparent window (upper-right): 1344×778px

**State key:** `S.lCard.url`, `S.lCard.visible`

**Setup:** Dashboard → Operator → L-Card section. Upload the file, press On.

**Sales angle:** The L-card keeps sponsor branding on-screen during live video without blocking the action. Commonly used by TV broadcasters. Can be fully animated. Highest-impact digital ad unit in the system.

---

### 3.2 Video Ad Overlay — Floating Ad on Live Feed

**Where:** An image or short video that floats over the live video feed for a set duration, then auto-hides.

**Format:** Image (JPG / PNG) or video (MP4 / WebM). Duration is configurable (default 15 seconds).

**State keys:** `S.vadUrl`, `S.vadType`, `S.vadDuration`, `S.vadCmd`

**Setup:** Dashboard → Video Source → Manual Ad Overlay section. Upload, set duration, press Show Ad on Feed. The operator can trigger this at any time.

**Sales angle:** Mid-roll style ad insertion on the live feed. Operator can trigger during stoppages in play (scrums, line-outs, injury time) for a clean presentation.

---

### 3.3 Score Bug — Corner Score Overlay During Video

**Where:** Compact score overlay (team names + live score + clock) pinned to the corner of the screen during video playback.

**Format:** System-generated UI element — no external upload needed.

**State key:** `S.showScoreBug`

**Sales angle:** Can incorporate a sponsor logo in the score bug design. Keeps sponsor branding adjacent to the live score at all times during video play.

---

## 4. Fan Engagement Monetization

These placements are tied to interactive fan features. Fans on their phones see the sponsor branding while engaging with the match.

### 4.1 Reaction Wall Sponsor

**Where:** Sponsor logo displayed at the bottom of the Reaction Wall sidebar on the broadcast display. Visible on-screen continuously while the Reaction Wall is active.

**Format:** Logo image (PNG recommended).

**State key:** `S.reactionWall.sponsorLogo`

**Setup:** Dashboard → Reaction Wall → Sponsor Logo section.

**Sales angle:** Every fan who picks up their phone to send reactions sees the sponsor's brand on the big screen alongside their emoji. High dwell time during engagement periods (break time, try celebrations).

---

### 4.2 Selfie Wall Sponsor — "Powered By"

**Where:** Sponsor logo shown as a "Powered by [Sponsor]" credit every time a fan selfie is displayed full-screen on the broadcast.

**Format:** Logo image (PNG with transparency recommended).

**State key:** `S.selfieWall.sponsorLogo`

**Setup:** Dashboard → Selfie Cam → Selfie Reveal Sponsor section.

**Sales angle:** Each selfie reveal is a unique, spontaneous moment shared between a fan and the crowd. The sponsor is co-credited on every reveal. Fans associate the warm emotional moment with the brand.

---

### 4.3 Live Poll — Sponsor QR Campaign

**Where:** Full-screen QR code overlay pushed to the broadcast display when a live poll is launched. Fans scan to vote. Results display as a branded animated bar chart.

**Format:** Auto-generated QR code. Custom headline, subtext, and results card.

**State keys:** `S.poll`, `S.qrOverlay`, `S.pollResultsOverlay`

**Setup:** Dashboard → Polls → Live Poll Builder.

**Sales angle:** Sell a sponsor the "Man of the Match" vote or a branded prediction poll. The QR screen, voting page, and results reveal are all sponsor-associated touchpoints.

---

### 4.4 Custom Campaign QR Overlay

**Where:** Full-screen QR code overlay linking to any URL. Custom headline and subtext shown above the QR code on the broadcast display.

**Format:** Custom URL → auto-generated QR. Text fields for headline and sub-text.

**State key:** `S.qrOverlay`

**Setup:** Dashboard → Polls → Custom Campaign section.

**Sales angle:** Point fans directly to a sponsor's website, ticket store, competition entry page, or social media. Measurable via link clicks / UTM parameters. Can be triggered at any moment by the operator.

---

## 5. Break-Time Monetization

These placements are designed for use during intervals, commercial breaks, and stoppages.

### 5.1 Ad Scheduler — Operator Playlist

**Where:** Full-screen sequential ad playback managed by the operator. Ads play one-by-one in a configured order on the broadcast display.

**Format:** Image (JPG / PNG / GIF), Video (MP4 / WebM), or Text Slide (headline + body text). Each item has a configurable duration in seconds.

**State keys:** `S.adSchedule[]`, `S.adScheduleActive`, `S.adScheduleCurrent`

**Setup:** Dashboard → Operator → Timeline section. Add items, drag to reorder, press Start to run. The operator can pause, skip, and navigate the playlist.

**Sales angle:** Sell a break-time ad package. Sponsors submit creative (image or video) and the operator runs the reel during half-time or commercial breaks. Track number of spots sold and total break duration.

---

### 5.2 Interval / Commercial Break Countdown

**Where:** Full-screen countdown timer shown on the broadcast display during break periods.

**Format:** Large countdown display with a configurable label (e.g. "HALF TIME", "BREAK") and sponsor branding can be embedded in the countdown overlay design.

**State key:** `S.commBreak`

**Setup:** Dashboard → Timer → Interval Countdown section. Set label, duration, press Start.

**Sales angle:** The countdown keeps fans engaged during breaks. A sponsor logo on the countdown screen gets sustained visibility for the entire break duration.

---

### 5.3 Full-Screen Announcement with Sponsor Logo

**Where:** Full-screen text announcement overlay pushed to the broadcast display. Optional sponsor logo shown below the announcement text.

**Format:** Text message (any string) + optional logo image.

**State keys:** `S.announcement`, `S.announcementLogo`

**Setup:** Dashboard → Announce → Full-Screen Overlay section.

**Sales angle:** Sponsor specific announcements — "HALFTIME courtesy of [Sponsor]", "Goal of the Match presented by [Sponsor]". Single-use activations can command premium pricing.

---

## 6. Production Branding

### 6.1 Papare / Production Credit

**Where:** Shown in the sponsor bar area as a production company credit.

**Format:** Logo image + text label (default: "PAPARE"). Visibility toggle.

**State key:** `S.papare`

**Setup:** Dashboard → Sponsors → Branding section. Upload logo, set text, press Show.

**Note:** This is typically used for the production company's own branding rather than a sponsor placement, but can be sold as a "broadcast partner" credit.

---

## 7. Sponsor Tier Package Ideas

Use this as a starting framework for selling packages:

### Platinum / Title Sponsor
- Principal Sponsor Strip placement (exclusive)
- Corner Bug (exclusive)
- Scoring / Celebration Sponsor (exclusive)
- L-Card (if video feed active)
- Reaction Wall sponsor logo
- Custom QR campaign (1 per match)

### Gold / Official Sponsor
- Official tier in Sponsor Strip
- Ad Slot A (full match)
- Video Ad Overlay (2× per half)
- Selfie Wall sponsor logo

### Silver / Partner Sponsor
- Partner tier in Sponsor Strip
- Ad Slot B or C (full match)
- Ad Scheduler spot (3× per break)

### Digital / Engagement Sponsor
- Live Poll sponsorship (Man of the Match vote)
- Selfie Wall "Powered By"
- Reaction Wall sponsor logo
- Custom QR campaign

### Break Sponsor
- Ad Scheduler playlist (all spots in one break)
- Interval countdown branding
- Full-screen announcement credit

---

## 8. Technical Notes for Sponsors

| Spec | Details |
|---|---|
| **Recommended logo format** | PNG with transparent background |
| **Recommended logo dimensions** | 400×200px minimum, 1200×600px ideal |
| **Ad Slot images** | Any aspect ratio; 1920×260px recommended |
| **Video format** | MP4 (H.264), WebM |
| **L-Card canvas** | 1920×1080px, transparent cut-out upper-right |
| **Corner Bug** | Any square or landscape logo; PNG alpha |
| **QR campaign URLs** | Any valid URL; add UTM params for tracking |
| **Live changes** | All placements update on the broadcast display within 1–2 seconds of saving |
| **Proof of placement** | Dashboard sidebar "On Air Now" panel shows every active placement in real time |

---

*Generated from the DoW Scoreboard System v10 — dashboard.html feature audit.*
