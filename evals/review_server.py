"""
Local page for listening to a match recording and labelling its speech.

    python -m evals.review_server      then open http://127.0.0.1:5005

Lists every recording in evals/clips/private/recordings that has a draft
transcript from evals/draft_transcript.py (<name>-api.tsv). Each draft line
plays its snippet and takes a label: player, radio, junk or unsure, plus the
language, what is actually said and its English meaning. Labels save as you
type to <name>-review.json next to the recording; clips are cut from them.

It listens on 127.0.0.1 only: the recordings hold other players' voices.
"""
import csv
import io
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from flask import Flask, abort, jsonify, request, send_file

REC = (Path(__file__).parent / "clips" / "private" / "recordings").resolve()
app = Flask(__name__)


def _sec(t: str) -> float:
    m, s = t.split(":")
    return int(m) * 60 + float(s)


def _recording(name: str) -> Path:
    p = (REC / name).resolve()
    if p.parent != REC or p.suffix != ".flac" or not p.exists():
        abort(404)
    return p


def _review_path(p: Path) -> Path:
    return p.with_name(p.stem + "-review.json")


@app.get("/api/recordings")
def recordings():
    return jsonify([p.name for p in sorted(REC.glob("*.flac")) if p.with_name(p.stem + "-api.tsv").exists()])


@app.get("/api/rows/<name>")
def rows(name):
    p = _recording(name)
    with open(p.with_name(p.stem + "-api.tsv"), encoding="utf-8") as f:
        draft = [{"start": _sec(r["start"]), "end": _sec(r["end"]), "language": r["language"],
                  "no_speech": float(r["no_speech"]), "logprob": float(r["logprob"]), "text": r["text"]}
                 for r in csv.DictReader(f, delimiter="\t")]
    rp = _review_path(p)
    review = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
    return jsonify({"draft": draft, "review": review, "duration": sf.info(p).duration})


@app.post("/api/review/<name>")
def save(name):
    p = _recording(name)
    rp = _review_path(p)
    tmp = rp.with_suffix(".tmp")
    tmp.write_text(json.dumps(request.get_json(), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(rp)
    return jsonify(ok=True)


@app.get("/audio/<name>")
def audio(name):
    p = _recording(name)
    info = sf.info(p)
    s = max(0.0, float(request.args["s"]))
    e = min(info.duration, float(request.args["e"]))
    if e <= s or e - s > 120:
        abort(400)
    x, sr = sf.read(p, start=int(s * info.samplerate), stop=int(e * info.samplerate), dtype="float32")
    if request.args.get("boost") == "1":
        x = x / max(np.abs(x).max(), 1e-4) * 0.9
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return send_file(buf, mimetype="audio/wav")


@app.get("/")
def index():
    return PAGE


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recording Review</title>
<style>
:root{--bg:#f6f6f4;--fg:#1b1b1b;--muted:#6b6b6b;--card:#fff;--line:#e2e2de;--accent:#2f6fde;--player:#1f8a4c;--radio:#8a6d1f;--junk:#a33;}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#e8e8e6;--muted:#9a9a96;--card:#1d1d1d;--line:#2e2e2c;--accent:#6f9cf0;--player:#4cc27f;--radio:#d0ad55;--junk:#e06a6a;}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,Segoe UI,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0 8px 0 0}select,input,button{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
button{cursor:pointer}button:hover{border-color:var(--accent)}.muted{color:var(--muted)}
main{padding:12px 16px;max-width:1100px;margin:0 auto}
.row{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:8px;padding:10px 12px;margin-bottom:8px;display:grid;grid-template-columns:auto 1fr;gap:6px 12px}
.row.playing{outline:2px solid var(--accent)}
.row[data-kind=player]{border-left-color:var(--player)}.row[data-kind=radio]{border-left-color:var(--radio)}.row[data-kind=junk]{border-left-color:var(--junk);opacity:.6}
.time{font-variant-numeric:tabular-nums;white-space:nowrap}.draft{font-size:15px}.meta{font-size:12px}
.controls{grid-column:1/-1;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.controls input.t{width:78px}.controls input.lang{width:100px}.controls input.text{flex:1;min-width:200px}
.kind button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
#status{margin-left:auto;font-size:12px}
</style></head><body>
<header><h1>Recording Review</h1>
<select id="rec"></select>
<label><input type="checkbox" id="boost" checked> Boost quiet clips</label>
<label>Pad <input id="pad" type="number" value="0.5" step="0.5" min="0" style="width:60px"> s</label>
<select id="filter"><option value="all">All rows</option><option value="todo">Unlabelled</option><option value="player">Player</option><option value="radio">Radio</option><option value="junk">Junk</option></select>
<button id="add">Add segment</button>
<span id="status" class="muted"></span></header>
<main id="list"></main>
<audio id="player"></audio>
<script>
const $ = s => document.querySelector(s), list = $('#list'), audio = $('#player');
let rec, draft = [], review = {}, saveTimer;
const fmt = t => `${Math.floor(t/60)}:${(t%60).toFixed(1).padStart(4,'0')}`;
const parse = v => { const [m,s] = String(v).split(':'); return s === undefined ? +m : +m*60 + +s; };

async function load() {
  const names = await (await fetch('/api/recordings')).json();
  $('#rec').innerHTML = names.map(n => `<option>${n}</option>`).join('');
  try { const last = localStorage.getItem('rec'); if (names.includes(last)) $('#rec').value = last; } catch {}
  open_();
}
async function open_() {
  rec = $('#rec').value; try { localStorage.setItem('rec', rec); } catch {}
  const d = await (await fetch('/api/rows/' + encodeURIComponent(rec))).json();
  draft = d.draft; review = d.review || {};
  render();
}
function rowsAll() {
  const r = draft.map((d, i) => ({id: 'd' + i, ...d}));
  for (const [id, v] of Object.entries(review)) if (id.startsWith('m')) r.push({id, start: v.start, end: v.end, language: '', text: '(added)', no_speech: 0, logprob: 0});
  return r.sort((a, b) => (review[a.id]?.start ?? a.start) - (review[b.id]?.start ?? b.start));
}
function render() {
  const f = $('#filter').value;
  list.innerHTML = '';
  for (const r of rowsAll()) {
    const v = review[r.id] || {};
    if (f === 'todo' && v.kind) continue;
    if (!['all','todo'].includes(f) && v.kind !== f) continue;
    const el = document.createElement('div');
    el.className = 'row'; el.dataset.kind = v.kind || ''; el.dataset.id = r.id;
    el.innerHTML = `
      <button class="play" title="Play">▶</button>
      <div><span class="time">${fmt(v.start ?? r.start)} – ${fmt(v.end ?? r.end)}</span>
        <span class="draft">${esc(r.text)}</span>
        <div class="meta muted">whisper: ${r.language || '–'} · no_speech ${r.no_speech.toFixed(2)} · logprob ${r.logprob.toFixed(2)}</div></div>
      <div class="controls">
        <button class="wide" title="Play 3 s either side">▶ wide</button>
        <input class="t s" value="${fmt(v.start ?? r.start)}" title="Start">
        <input class="t e" value="${fmt(v.end ?? r.end)}" title="End">
        <span class="kind">${['player','radio','junk','unsure'].map(k => `<button data-k="${k}" class="${v.kind===k?'on':''}">${k}</button>`).join('')}</span>
        <input class="lang" placeholder="language" value="${esc(v.language ?? (r.language || ''))}">
        <input class="text" placeholder="What is actually said (original language)" value="${esc(v.text ?? '')}">
        <input class="text en" placeholder="English meaning" value="${esc(v.english ?? '')}">
      </div>`;
    list.appendChild(el);
  }
}
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function row(el) { return rowsAll().find(r => r.id === el.dataset.id); }
function edit(el, patch) {
  const id = el.dataset.id; review[id] = {...(review[id] || {}), ...patch};
  if (patch.kind !== undefined) el.dataset.kind = patch.kind;
  clearTimeout(saveTimer); $('#status').textContent = 'Saving…';
  saveTimer = setTimeout(async () => {
    const r = await fetch('/api/review/' + encodeURIComponent(rec), {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(review)});
    $('#status').textContent = r.ok ? 'Saved' : 'Save failed';
  }, 400);
}
function play(el, extra) {
  const pad = +$('#pad').value + extra;
  const s = parse(el.querySelector('.s').value) - pad, e = parse(el.querySelector('.e').value) + pad;
  document.querySelectorAll('.row.playing').forEach(x => x.classList.remove('playing'));
  el.classList.add('playing');
  audio.src = `/audio/${encodeURIComponent(rec)}?s=${Math.max(0, s)}&e=${e}&boost=${$('#boost').checked ? 1 : 0}`;
  audio.play();
}
audio.onended = () => document.querySelectorAll('.row.playing').forEach(x => x.classList.remove('playing'));
list.addEventListener('click', ev => {
  const el = ev.target.closest('.row'); if (!el) return;
  if (ev.target.classList.contains('play')) play(el, 0);
  else if (ev.target.classList.contains('wide')) play(el, 3);
  else if (ev.target.dataset.k) {
    const k = ev.target.dataset.k, on = review[el.dataset.id]?.kind === k ? '' : k;
    el.querySelectorAll('.kind button').forEach(b => b.classList.toggle('on', b.dataset.k === on));
    edit(el, {kind: on});
  }
});
list.addEventListener('change', ev => {
  const el = ev.target.closest('.row'); if (!el) return;
  const c = ev.target.classList;
  if (c.contains('s')) edit(el, {start: parse(ev.target.value)});
  else if (c.contains('e')) edit(el, {end: parse(ev.target.value)});
  else if (c.contains('lang')) edit(el, {language: ev.target.value});
  else if (c.contains('en')) edit(el, {english: ev.target.value});
  else if (c.contains('text')) edit(el, {text: ev.target.value});
});
$('#add').onclick = () => {
  const t = parse(prompt('Start time (m:ss)', '0:00') || 'x'); if (isNaN(t)) return;
  const id = 'm' + Date.now(); review[id] = {start: t, end: t + 3};
  render(); edit(list.querySelector(`[data-id="${id}"]`), {});
};
$('#rec').onchange = open_; $('#filter').onchange = render;
load();
</script></body></html>"""

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5005)
