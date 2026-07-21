#!/usr/bin/env python3
"""
Metal Drum MIDI Generator v3
  - DRUM_STYLE switch: "thrash" | "power_metal" | "groove"
  - graded double-kick per section (verse med -> chorus dense -> solo densest)
  - ride/china cymbal language (aggressive), NO cross-stick, ghost notes off
  - graded fills + section-start crash
General MIDI drum map.  pip install mido  ->  python drum_gen.py  ->  drums.mid
"""

import random
from mido import Message, MidiFile, MidiTrack, MetaMessage, bpm2tempo

# ==================== SONG ====================
TEMPO_BPM     = 170
BEATS_PER_BAR = 4
SUBDIV        = 4
SEED          = 7

# Tornado-of-Souls-shaped arrangement (edit freely)
SONG = [
    ("intro",   16),
    ("verse",   24),
    ("chorus",  16),
    ("verse",   24),
    ("chorus",  16),
    ("solo",    56),
    ("chorus",  16),
    ("outro",   16),
]

# ---- pick the drum vocabulary. change this ONE line to reshape the whole kit feel. ----
DRUM_STYLE = "thrash"          # "thrash" | "power_metal" | "groove"

# ---- graded double-kick intensity per section (0=sparse .. 3=constant 16ths) ----
DOUBLE_KICK = {
    "intro":  0,
    "verse":  1,               # medium
    "chorus": 2,               # dense
    "solo":   3,               # densest
    "outro":  0,
}

# ---- feel switches ----
CRASH_ON_SECTION_START = True
FILL_EVERY             = 4
BIG_FILL_AT_SECTION_END= True
FILL_SECTIONS          = ("verse","chorus","solo")
VARIATION              = 0.6   # metal wants tighter/less random than funk; keep modest
GHOST_NOTES            = 0.0   # 0 = none (metal default). raise for subtle snare ghosts.
# =============================================

# General MIDI drums
KICK=36; SNARE=38; CHH=42; OHH=46
RIDE=51; RIDE_BELL=53; CRASH=49; CRASH2=57; CHINA=52; SPLASH=55
TOM_HI=50; TOM_MID=47; TOM_LO=43

SLOTS_PER_BAR = SUBDIV * BEATS_PER_BAR
def every(n, off=0, upto=SLOTS_PER_BAR): return list(range(off, upto, n))
def on_beats(*b): return [(x-1)*SUBDIV for x in b]
def add_hit(h, note, slot, vel): h.setdefault(note, []).append((slot, max(1,min(127,vel))))

# ---------- KICK: style x level ----------
def kick_slots(style, level):
    if level <= 0:
        return on_beats(1,3)                                  # sparse pulse
    if style == "power_metal":
        return {1: every(2), 2: every(1), 3: every(1)}[min(level,3)]   # 8th -> 16th wall
    if style == "thrash":
        gallop = [b*SUBDIV+o for b in range(BEATS_PER_BAR) for o in (0,1,2)]  # 16-16-8 gallop
        return {1: every(2), 2: gallop, 3: every(1)}[min(level,3)]
    if style == "groove":
        return {1: [0,3,6,10], 2: [0,2,3,8,10,11], 3: every(2)}[min(level,3)]  # syncopated, heavy
    return every(2)

def kick_vel(style):
    return {"thrash":106, "power_metal":110, "groove":114}.get(style,108)

# ---------- CYMBALS per section (ride/china emphasis, aggressive) ----------
def cymbals(section, bar_in_sec, rng):
    h = {}
    if section == "intro":
        h.setdefault(RIDE, []).extend((s,74) for s in every(4))           # sparse ride quarters
    elif section == "verse":
        h.setdefault(RIDE, []).extend((s,84) for s in every(2))           # ride 8ths
        for s in on_beats(1,3): add_hit(h, RIDE_BELL, s, 96)              # bell accents on 1&3
    elif section == "chorus":
        h.setdefault(RIDE, []).extend((s,92) for s in every(2))           # driving ride 8ths
        if bar_in_sec % 4 == 0: add_hit(h, CHINA, 0, 112)                # china accent every 4 bars
    elif section == "solo":
        h.setdefault(RIDE, []).extend((s,90) for s in every(2))           # ride 8ths under solo
        add_hit(h, CHINA, 0, 110)                                        # china on every downbeat
        if bar_in_sec % 2 == 1: add_hit(h, CHINA, 8, 104)                # + mid-bar china accent
    elif section == "outro":
        h.setdefault(RIDE, []).extend((s,80) for s in every(4))
        add_hit(h, CRASH, 0, 110)
    return h

# ---------- SNARE (metal backbeat, no cross-stick) ----------
def snare_slots(section):
    if section == "intro": return []                          # drums lay back on the harmonic intro
    return on_beats(2,4)                                      # standard hard backbeat

def snare_vel(section):
    return {"verse":112, "chorus":120, "solo":116, "outro":110}.get(section,112)

# ---------- build one bar ----------
def build_bar(section, bar_in_sec, total, rng):
    h = {}
    lvl = DOUBLE_KICK.get(section, 0)
    for s in kick_slots(DRUM_STYLE, lvl):
        add_hit(h, KICK, s, kick_vel(DRUM_STYLE) + rng.randint(-4,4))
    for s in snare_slots(section):
        add_hit(h, SNARE, s, snare_vel(section) + rng.randint(-4,3))
    for note, lst in cymbals(section, bar_in_sec, rng).items():
        h.setdefault(note, []).extend(lst)
    return h

# ---------- metal variation (tight; no funk ghosts, no cross-stick) ----------
def vary(h, section, bar_in_sec, rng):
    if VARIATION <= 0: return h
    p = VARIATION
    if section in ("verse","chorus","solo"):
        for cand in (7,11,15,3):
            if rng.random() < 0.14*p: add_hit(h, KICK, cand, kick_vel(DRUM_STYLE)-6)
    if section in ("chorus","solo") and rng.random() < 0.15*p:
        add_hit(h, CHINA, rng.choice([4,12]), 100)
    if GHOST_NOTES > 0 and section in ("verse","solo"):
        for cand in (6,14):
            if rng.random() < GHOST_NOTES: add_hit(h, SNARE, cand, 38+rng.randint(-6,8))
    for cym in (RIDE, OHH):
        if cym in h:
            h[cym] = [(s, min(127, v + (10 if s%SUBDIV==0 else 0) + rng.randint(-3,3))) for (s,v) in h[cym]]
    return h

# ---------- fills ----------
def small_fill(rng):
    h = {}
    if rng.random() < 0.5:
        for s in (12,13,14,15):
            if rng.random() < 0.8: add_hit(h, SNARE, s, 104+rng.randint(-6,8))
    else:
        add_hit(h,TOM_MID,12,108); add_hit(h,TOM_MID,13,108)
        add_hit(h,TOM_LO,14,112);  add_hit(h,TOM_LO,15,112)
    add_hit(h,KICK,12,kick_vel(DRUM_STYLE)); add_hit(h,KICK,14,kick_vel(DRUM_STYLE))
    return h, 12

def big_fill(rng, intensity=1.0):
    h = {}
    for s in range(0,8):
        add_hit(h, SNARE, s, int(104*intensity)+rng.randint(-6,8))
    toms=[TOM_HI,TOM_HI,TOM_MID,TOM_MID,TOM_LO,TOM_LO]
    for i,s in enumerate(range(8,14)): add_hit(h,toms[i],s,int(112*intensity))
    for s in (8,10,12): add_hit(h,KICK,s,kick_vel(DRUM_STYLE))
    return h, 0

def clear_groove_from(h, frm):
    for note in (SNARE,CHH,OHH,RIDE,RIDE_BELL):
        if note in h: h[note] = [(s,v) for (s,v) in h[note] if s < frm]
    return h

# ---------- assemble ----------
random.seed(SEED)
TPQ=480; slot_ticks=TPQ//SUBDIV
mid=MidiFile(ticks_per_beat=TPQ); tr=MidiTrack(); mid.tracks.append(tr)
tr.append(MetaMessage('set_tempo',tempo=bpm2tempo(TEMPO_BPM),time=0))
tr.append(MetaMessage('time_signature',numerator=BEATS_PER_BAR,denominator=4,time=0))
tr.append(MetaMessage('track_name',name=f'Drums v3 [{DRUM_STYLE}]',time=0))

raw=[]; bar_cursor=0
for section, bars in SONG:
    for b in range(bars):
        base = bar_cursor*SLOTS_PER_BAR*slot_ticks
        rng = random.Random(SEED*7919 + bar_cursor*104729)
        h = build_bar(section, b, bars, rng)
        h = vary(h, section, b, rng)
        is_last = (b==bars-1)
        if section in FILL_SECTIONS:
            if BIG_FILL_AT_SECTION_END and is_last and bars>=2:
                h=clear_groove_from(h,0); fh,_=big_fill(rng,1.1 if section=='chorus' else 1.0)
                for n,l in fh.items(): h.setdefault(n,[]).extend(l)
            elif FILL_EVERY and (b+1)%FILL_EVERY==0 and not is_last:
                fh,frm=small_fill(rng); h=clear_groove_from(h,frm)
                for n,l in fh.items(): h.setdefault(n,[]).extend(l)
        if CRASH_ON_SECTION_START and b==0:
            add_hit(h,CRASH,0,120); add_hit(h,KICK,0,kick_vel(DRUM_STYLE)+4)
        for note,l in h.items():
            for (s,vel) in l:
                on=base+s*slot_ticks
                raw.append((on,note,vel,True)); raw.append((on+slot_ticks-5,note,0,False))
        bar_cursor+=1

raw.sort(key=lambda e:(e[0],e[3]))
t=0
for (tick,note,vel,is_on) in raw:
    tr.append(Message('note_on' if is_on else 'note_off',note=note,velocity=vel,
                      time=max(0,tick-t),channel=9)); t=tick
mid.save('drums.mid')

print(f"style       : {DRUM_STYLE}")
print(f"double-kick : {DOUBLE_KICK}")
print("arrangement :"," -> ".join(f"{s}({b})" for s,b in SONG))
print(f"tempo       : {TEMPO_BPM} BPM   total bars: {sum(b for _,b in SONG)}   hits: {len([e for e in raw if e[3]])}")
print("saved       : drums.mid")
