#!/usr/bin/env python3
"""
Song-structure Drum MIDI Generator v2
  - per-section drum styles
  - PER-BAR variation (kick/hat/ghost-note perturbations, non-mechanical)
  - graded fills: small fill every N bars + big fill at section end
  - unified crash on every section's first downbeat
General MIDI drum map.  pip install mido  ->  python drum_gen.py  ->  drums.mid
"""

import random
from mido import Message, MidiFile, MidiTrack, MetaMessage, bpm2tempo

# ==================== SONG ====================
TEMPO_BPM     = 200
BEATS_PER_BAR = 4
SUBDIV        = 4          # 4 = 16th grid
SEED          = 7

SONG = [
    ("intro",   4),
    ("verse",   8),
    ("chorus",  8),
    ("solo",    8),
    ("chorus",  8),
    ("verse",   8),
    ("outro",   4),
]

# ---- global feel switches ----
CRASH_ON_SECTION_START = True   # crash + kick on the first downbeat of every section
FILL_EVERY             = 4      # small fill every N bars within a section (0 = off)
BIG_FILL_AT_SECTION_END= True   # big fill on the last bar of multi-bar sections
VARIATION              = 0.85   # 0 = identical bars, 1 = max per-bar perturbation
FILL_SECTIONS          = ("verse","chorus","solo")  # which sections get fills
# =============================================

# ---- General MIDI drum notes ----
KICK=36; SNARE=38; RIM=37; CHH=42; OHH=46; PHH=44
RIDE=51; CRASH=49; CRASH2=57; TOM_HI=50; TOM_MID=47; TOM_LO=43; CHINA=52

SLOTS_PER_BAR = SUBDIV * BEATS_PER_BAR

def every(n, offset=0, upto=SLOTS_PER_BAR): return list(range(offset, upto, n))
def on_beats(*beats): return [(b-1)*SUBDIV for b in beats]

# ---- base STYLES (one bar) ----
def style_intro(b, total, rng):
    h={}
    h.setdefault(CHH,[]).extend((s,70) for s in every(4))
    h.setdefault(KICK,[]).extend((s,100) for s in on_beats(1,3))
    if b>=total-1:
        h.setdefault(SNARE,[]).extend((s,90) for s in every(2,offset=8))
    return h

def style_verse(b, total, rng):
    h={}
    h.setdefault(CHH,[]).extend((s,72) for s in every(2))
    h.setdefault(KICK,[]).extend([(0,105),(6,95),(10,100)])
    h.setdefault(RIM,[]).extend((s,88) for s in on_beats(2,4))
    return h

def style_chorus(b, total, rng):
    h={}
    h.setdefault(OHH,[]).extend((s,96) for s in every(2))
    h.setdefault(KICK,[]).extend((s,112) for s in every(2))
    h.setdefault(SNARE,[]).extend((s,118) for s in on_beats(2,4))
    return h

def style_solo(b, total, rng):
    h={}
    h.setdefault(RIDE,[]).extend((s,90) for s in every(2))
    h.setdefault(KICK,[]).extend((s,108) for s in every(1) if s%4!=3)
    h.setdefault(SNARE,[]).extend((s,115) for s in on_beats(2,4))
    return h

def style_outro(b, total, rng):
    h={}
    h.setdefault(KICK,[]).extend((s,105) for s in on_beats(1,3))
    h.setdefault(SNARE,[]).extend((s,108) for s in on_beats(3))
    h.setdefault(RIDE,[]).extend((s,80) for s in every(4))
    return h

STYLES={"intro":style_intro,"verse":style_verse,"chorus":style_chorus,
        "solo":style_solo,"outro":style_outro}

# ---- per-bar VARIATION: perturb a base pattern without breaking its feel ----
def add_hit(h, note, slot, vel): h.setdefault(note,[]).append((slot,vel))

def vary(h, section, bar_in_sec, rng):
    """apply small, style-appropriate perturbations governed by VARIATION."""
    if VARIATION <= 0: return h
    p = VARIATION

    # extra kick syncopation (all driving sections)
    if section in ("chorus","solo","verse"):
        for cand in (7, 11, 14, 3):
            if rng.random() < 0.18*p:
                add_hit(h, KICK, cand, 96+rng.randint(-6,8))

    # ghost snare notes (quiet 16th snares) in verse/solo -> human feel
    if section in ("verse","solo"):
        for cand in (2,6,10,14,7,13):
            if rng.random() < 0.15*p:
                add_hit(h, SNARE, cand, 40+rng.randint(-8,10))  # ghost = low velocity

    # occasional open-hat accent replacing a closed hat (verse/intro)
    if section in ("verse","intro") and CHH in h:
        if rng.random() < 0.35*p:
            hats=[s for (s,v) in h[CHH]]
            if hats:
                sw=rng.choice(hats)
                h[CHH]=[(s,v) for (s,v) in h[CHH] if s!=sw]
                add_hit(h, OHH, sw, 88)

    # hat dynamics: accent the downbeats slightly, breathe on off-beats
    for hat in (CHH, OHH, RIDE):
        if hat in h:
            newlist=[]
            for (s,v) in h[hat]:
                accent = 12 if s%SUBDIV==0 else (-6 if s%2==1 else 0)
                jitter = rng.randint(-4,4) if p>0 else 0
                newlist.append((s, max(1,min(127, v+int(accent*p)+jitter)))) 
            h[hat]=newlist

    # every other bar, drop one kick to avoid total uniformity
    if bar_in_sec%2==1 and KICK in h and len(h[KICK])>2 and rng.random()<0.5*p:
        h[KICK].pop(rng.randrange(len(h[KICK])))
    return h

# ---- graded fills ----
def small_fill(rng):
    """light 1-beat fill (last beat): a few snares or a quick tom tap."""
    h={}
    if rng.random()<0.5:
        for s in (12,13,14,15):
            if rng.random()<0.7: add_hit(h,SNARE,s,90+rng.randint(-8,10))
    else:
        add_hit(h,TOM_MID,12,100); add_hit(h,TOM_MID,13,100)
        add_hit(h,TOM_LO,14,104);  add_hit(h,TOM_LO,15,104)
    add_hit(h,KICK,12,100)
    return h, 12   # returns fill hits + slot from which to clear the base groove

def big_fill(rng, intensity=1.0):
    """heavy half-bar tom roll into a crash on next downbeat."""
    h={}
    for s in range(0,8):
        if rng.random()<0.6: add_hit(h,SNARE,s,int(95*intensity)+rng.randint(-8,8))
    toms=[TOM_HI,TOM_HI,TOM_MID,TOM_MID,TOM_LO,TOM_LO]
    for i,s in enumerate(range(8,14)): add_hit(h,toms[i],s,int(106*intensity))
    add_hit(h,KICK,8,100); add_hit(h,KICK,11,100)
    return h, 8

def clear_groove_from(h, from_slot, keep=(KICK,)):
    """remove melodic groove voices at/after from_slot so a fill can take over."""
    for note in (SNARE,CHH,OHH,RIDE,RIM):
        if note in h:
            h[note]=[(s,v) for (s,v) in h[note] if s<from_slot]
    return h

# ---- assemble ----
random.seed(SEED)
TPQ=480; slot_ticks=TPQ//SUBDIV
mid=MidiFile(ticks_per_beat=TPQ); track=MidiTrack(); mid.tracks.append(track)
track.append(MetaMessage('set_tempo',tempo=bpm2tempo(TEMPO_BPM),time=0))
track.append(MetaMessage('time_signature',numerator=BEATS_PER_BAR,denominator=4,time=0))
track.append(MetaMessage('track_name',name='Drums v2',time=0))

raw=[]; bar_cursor=0
for si,(section,bars) in enumerate(SONG):
    style_fn=STYLES[section]
    for b in range(bars):
        base_tick=bar_cursor*SLOTS_PER_BAR*slot_ticks
        rng=random.Random(SEED*7919 + bar_cursor*104729)   # unique, reproducible per bar

        h=style_fn(b,bars,rng)
        h=vary(h,section,b,rng)

        is_last=(b==bars-1)
        # graded fills
        if section in FILL_SECTIONS:
            if BIG_FILL_AT_SECTION_END and is_last and bars>=2:
                h=clear_groove_from(h,8); fh,_=big_fill(rng,1.1 if section=='chorus' else 1.0)
                for n,l in fh.items(): h.setdefault(n,[]).extend(l)
            elif FILL_EVERY and (b+1)%FILL_EVERY==0 and not is_last:
                fh,frm=small_fill(rng); h=clear_groove_from(h,frm)
                for n,l in fh.items(): h.setdefault(n,[]).extend(l)

        # crash on section start (first bar, downbeat)
        if CRASH_ON_SECTION_START and b==0:
            add_hit(h,CRASH,0,118); add_hit(h,KICK,0,110)

        for note,l in h.items():
            for (s,vel) in l:
                on=base_tick+s*slot_ticks; vel=max(1,min(127,vel))
                raw.append((on,note,vel,True)); raw.append((on+slot_ticks-5,note,0,False))
        bar_cursor+=1

raw.sort(key=lambda e:(e[0],e[3]))
t=0
for (tick,note,vel,is_on) in raw:
    track.append(Message('note_on' if is_on else 'note_off',note=note,velocity=vel,
                         time=max(0,tick-t),channel=9)); t=tick
mid.save('drums.mid')

print("arrangement :"," -> ".join(f"{s}({b})" for s,b in SONG))
print(f"variation={VARIATION}  fill_every={FILL_EVERY}  big_fill_end={BIG_FILL_AT_SECTION_END}  section_crash={CRASH_ON_SECTION_START}")
print(f"total bars  : {sum(b for _,b in SONG)}   hits: {len([e for e in raw if e[3]])}")
print("saved       : drums.mid")