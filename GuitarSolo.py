#!/usr/bin/env python3
"""
Power Metal Solo Generator v4
  - chord-progression aware (one chord per bar)
  - configurable chord-tone anchoring
  - voice-leading between bars
  - per-bar phrase shapes
  - PER-BAR ending articulation: run / hold / bend / vibrato
Needs mido:  pip install mido    ->    python pm_solo.py  ->  pm_solo.mid
"""

import math, random
from mido import Message, MidiFile, MidiTrack, MetaMessage, bpm2tempo

# ==================== PARAMETERS ====================
KEY_ROOT   = 64                 # tonal center, MIDI. E4=64.
SCALE_NAME = "harmonic_minor"
TEMPO_BPM  = 200
SUBDIV     = 4                  # notes/beat: 4=16ths, 6=16th-trip, 8=32nds
BEATS_PER_BAR = 4
GATE       = 0.92
SEED       = 7
BEND_RANGE = 2                  # your guitar VSTi pitch-bend range, semitones

ANCHOR_MODE = "strong"          # "downbeat" | "strong" | "all"
VOICE_LEADING = True

# articulation tuning
BEND_SEMITONES   = 2.0          # how far "bend" pushes (2 = whole step)
VIBRATO_DEPTH    = 0.30         # vibrato depth in semitones (0.25-0.5 typical)
VIBRATO_RATE_HZ  = 5.5          # vibrato speed
VIBRATO_DELAY    = 0.35         # fraction of the held note before vibrato starts

PROGRESSION = [
    "Em", "C", "G", "D",
    "Am", "B7", "Em", "B7",
]

# phrase shape per bar (None = random that bar)
PHRASE_PLAN = [
    "line_up",  "line_down", "seq_up",  "pedal",
    "seq_up",   "seq_down",  "arp_up",  "seq_down",
]

# NEW: how each bar ENDS. same length as PROGRESSION.
#   "run"     = no special ending, notes keep going into next bar (default feel)
#   "hold"    = last note of the bar becomes a sustained note
#   "bend"    = sustained note + whole-step bend
#   "vibrato" = sustained note + delayed vibrato
# For hold/bend/vibrato, the last HOLD_BEATS of that bar collapse into ONE
# sustained note (snapped to a chord tone -- it's a landing point).
PHRASE_END_PLAN = [
    "run",   "hold",    "run",     "bend",
    "run",   "vibrato", "run",     "bend",
]
HOLD_BEATS = 1                  # length of a hold/bend/vibrato ending, in beats
# ===================================================

SCALES = {
    "natural_minor":     [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor":    [0, 2, 3, 5, 7, 8, 11],
    "phrygian_dominant": [0, 1, 4, 5, 7, 8, 10],
    "dorian":            [0, 2, 3, 5, 7, 9, 10],
    "major":             [0, 2, 4, 5, 7, 9, 11],
}
NOTE_TO_PC = {"C":0,"C#":1,"Db":1,"D":2,"D#":3,"Eb":3,"E":4,"F":5,"F#":6,"Gb":6,
              "G":7,"G#":8,"Ab":8,"A":9,"A#":10,"Bb":10,"B":11}
CHORD_INTERVALS = {"":[0,4,7],"maj":[0,4,7],"m":[0,3,7],"min":[0,3,7],"dim":[0,3,6],
                   "aug":[0,4,8],"5":[0,7],"7":[0,4,7,10],"m7":[0,3,7,10],"maj7":[0,4,7,11]}

random.seed(SEED)
TPQ   = 480
scale = SCALES[SCALE_NAME]

def parse_chord(sym):
    if len(sym) >= 2 and sym[1] in ("#", "b"):
        return NOTE_TO_PC[sym[:2]], sym[2:]
    return NOTE_TO_PC[sym[:1]], sym[1:]

def build_pool(root, scale, octaves=3):
    return [root + o*12 + iv for o in range(octaves) for iv in scale]

POOL = build_pool(KEY_ROOT, scale, octaves=3)
TOP  = len(POOL) - 1

def chord_pcs_of(sym):
    pc, qual = parse_chord(sym)
    ivs = CHORD_INTERVALS.get(qual, CHORD_INTERVALS["m"])
    return {(pc + iv) % 12 for iv in ivs}, pc

def is_ct(p, pcs):  return (p % 12) in pcs
def nearest_ct(pool_idx, pcs):
    best, bd = pool_idx, 999
    for j in range(len(POOL)):
        if is_ct(POOL[j], pcs):
            d = abs(j - pool_idx)
            if d < bd: best, bd = j, d
    return best

def sh_line_up(s, n):   return [s + i for i in range(n)]
def sh_line_down(s, n): return [s - i for i in range(n)]
def sh_seq_up(s, n):
    out=[]; g=0
    while len(out)<n:
        for k in range(4): out.append(s+g+k)
        g+=1
    return out[:n]
def sh_seq_down(s, n):
    out=[]; g=0
    while len(out)<n:
        for k in range(4): out.append(s-g-k)
        g+=1
    return out[:n]
def sh_pedal(s, n):
    out=[]; i=0
    while len(out)<n:
        out.append(s+i); out.append(TOP); i+=1
    return out[:n]
def sh_arp_up(s, n):   return [s + 2*i for i in range(n)]
def sh_arp_down(s, n): return [s - 2*i for i in range(n)]
SHAPES = {"line_up":sh_line_up,"line_down":sh_line_down,"seq_up":sh_seq_up,
          "seq_down":sh_seq_down,"pedal":sh_pedal,"arp_up":sh_arp_up,"arp_down":sh_arp_down}

SLOTS_PER_BAR = SUBDIV * BEATS_PER_BAR

def anchor_positions():
    if ANCHOR_MODE == "downbeat": return [0]
    if ANCHOR_MODE == "all":      return list(range(BEATS_PER_BAR))
    return [0, 2] if BEATS_PER_BAR >= 4 else [0]

def make_bar(chord_pcs, shape_name, start_rung, phrase_seed):
    rng = random.Random(phrase_seed)
    if shape_name is None: shape_name = rng.choice(list(SHAPES.keys()))
    idx = SHAPES[shape_name](start_rung, SLOTS_PER_BAR)[:SLOTS_PER_BAR]
    while len(idx) < SLOTS_PER_BAR: idx.append(idx[-1])
    idx = [max(0, min(TOP, i)) for i in idx]
    for beat in anchor_positions():
        idx[beat*SUBDIV] = nearest_ct(idx[beat*SUBDIV], chord_pcs)
    return idx

# ---- build a per-slot plan for the whole solo ----
events = []
prev_last = None
hold_slots = HOLD_BEATS * SUBDIV

for bar, sym in enumerate(PROGRESSION):
    pcs, _ = chord_pcs_of(sym)
    shape_name = PHRASE_PLAN[bar] if (PHRASE_PLAN and bar < len(PHRASE_PLAN)) else None
    if VOICE_LEADING and prev_last is not None:
        start_rung = nearest_ct(prev_last, pcs)
    else:
        start_rung = random.Random(SEED + bar*101).randint(2, TOP-2)
    bar_idx = make_bar(pcs, shape_name, start_rung, SEED + bar*101)

    end_art = PHRASE_END_PLAN[bar] if (PHRASE_END_PLAN and bar < len(PHRASE_END_PLAN)) else "run"
    bar_start_slot = bar * SLOTS_PER_BAR

    if end_art == "run":
        for s in range(SLOTS_PER_BAR):
            events.append({"slot": bar_start_slot + s, "pitch": POOL[bar_idx[s]],
                           "len": 1, "art": "run"})
        prev_last = bar_idx[-1]
    else:
        head = SLOTS_PER_BAR - hold_slots
        for s in range(head):
            events.append({"slot": bar_start_slot + s, "pitch": POOL[bar_idx[s]],
                           "len": 1, "art": "run"})
        sustain_idx = bar_idx[head] if head < len(bar_idx) else bar_idx[-1]
        sustain_idx = nearest_ct(sustain_idx, pcs)
        events.append({"slot": bar_start_slot + head, "pitch": POOL[sustain_idx],
                       "len": hold_slots, "art": end_art})
        prev_last = sustain_idx

# ---- render ----
mid   = MidiFile(ticks_per_beat=TPQ)
track = MidiTrack(); mid.tracks.append(track)
track.append(MetaMessage('set_tempo', tempo=bpm2tempo(TEMPO_BPM), time=0))
track.append(MetaMessage('time_signature', numerator=BEATS_PER_BAR, denominator=4, time=0))
track.append(MetaMessage('track_name', name='PM Solo v4', time=0))

slot = TPQ // SUBDIV
t = 0
def add(mt, tick, **kw):
    global t
    track.append(Message(mt, time=max(0, tick - t), **kw)); t = tick

def emit_bend(start_tick, dur_ticks, semis):
    steps = 24; val = 0
    for s in range(steps + 1):
        frac = s / steps
        val = max(-8192, min(8191, int(round((frac*semis/BEND_RANGE)*8192))))
        add('pitchwheel', start_tick + int(dur_ticks*0.5*frac), pitch=val)
    add('pitchwheel', start_tick + dur_ticks, pitch=val)
    return True

def emit_vibrato(start_tick, dur_ticks):
    delay = int(dur_ticks * VIBRATO_DELAY)
    n = max(8, int(dur_ticks / 20))
    for k in range(n + 1):
        tick = start_tick + delay + int((dur_ticks - delay) * k / n)
        phase = 2*math.pi * VIBRATO_RATE_HZ * ((tick - start_tick)/TPQ) * (TEMPO_BPM/60.0)
        semis = VIBRATO_DEPTH * math.sin(phase)
        val = max(-8192, min(8191, int(round((semis/BEND_RANGE)*8192))))
        add('pitchwheel', tick, pitch=val)
    return True

for ev in events:
    pitch = ev["pitch"]
    on = ev["slot"] * slot
    dur = ev["len"] * slot
    if ev["art"] == "run":
        vel = 112 if (ev["slot"] % SUBDIV == 0) else random.randint(84, 100)
        add('note_on',  on, note=pitch, velocity=vel)
        add('note_off', on + int(slot*GATE), note=pitch, velocity=0)
    else:
        add('note_on', on, note=pitch, velocity=115)
        needs_reset = False
        if ev["art"] == "bend":
            needs_reset = emit_bend(on, dur, BEND_SEMITONES)
        elif ev["art"] == "vibrato":
            needs_reset = emit_vibrato(on, dur)
        # "hold" = just sustain, no wheel
        add('note_off', on + int(dur*0.97), note=pitch, velocity=0)
        if needs_reset:
            add('pitchwheel', on + dur, pitch=0)

mid.save('pm_solo.mid')

print(f"progression : {' | '.join(PROGRESSION)}")
print(f"phrase plan : {PHRASE_PLAN}")
print(f"end plan    : {PHRASE_END_PLAN}   (hold={HOLD_BEATS} beat)")
print(f"anchor/VL   : {ANCHOR_MODE} / {VOICE_LEADING}")
print(f"bars        : {len(PROGRESSION)}, events: {len(events)}")
print("saved       : pm_solo.mid")