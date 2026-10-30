"""Local production dashboard (Python standard library only, no installs).

    python -m studio dashboard        ->  http://127.0.0.1:8765

Lists every episode with its pipeline progress, shows scripts, shots, QC
reports and the rendered video, and runs render / QC / approve / export.
It only listens on this computer and never publishes anything.
"""
from __future__ import annotations

import html
import json
import mimetypes
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, episode, pipeline, qc

JOB = {"name": None, "log": [], "running": False, "error": None, "finished": None}
LOCK = threading.Lock()
MEDIA_ROOTS = [config.BUILD_DIR, config.EXPORTS_DIR, config.CHARACTERS_DIR]

CSS = """
:root{--bg:#FBF6EC;--card:#fff;--ink:#2A1A12;--muted:#7A6A60;--line:#E8DCCB;--purple:#5E3594;--pink:#F6A8D3;
--green:#3E8E4A;--amber:#C98A12;--red:#B23A2E;--roach:#8B3A1E}
@media (prefers-color-scheme:dark){:root{--bg:#17120F;--card:#221B17;--ink:#F3E9DD;--muted:#B3A496;--line:#3A2F28}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
header{padding:18px 24px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header h1{font-size:20px;margin:0}header a{color:var(--purple);text-decoration:none;font-weight:600}
main{padding:20px 24px;max-width:1200px;margin:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}
.card h3{margin:0 0 4px;font-size:17px}.muted{color:var(--muted)}.id{font:600 12px ui-monospace,monospace;color:var(--roach)}
.stages{display:flex;gap:3px;margin:10px 0}.st{flex:1;height:8px;border-radius:4px;background:var(--line)}
.st.done{background:var(--green)}.st.in_progress,.st.stale{background:var(--amber)}.st.failed{background:var(--red)}
table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;color:var(--muted)}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;background:var(--line)}
.pill.done,.pill.PASS{background:#D9F2DC;color:#1E5E28}.pill.failed,.pill.FAIL{background:#F8D7D3;color:#8A2219}
.pill.stale,.pill.in_progress,.pill.WARN{background:#FBEBC7;color:#7A5300}
.cols{display:grid;grid-template-columns:minmax(0,360px) 1fr;gap:20px}@media(max-width:800px){.cols{grid-template-columns:1fr}}
video,img.sheet{width:100%;border-radius:12px;border:1px solid var(--line);background:#000}
button,.btn{background:var(--purple);color:#fff;border:0;border-radius:10px;padding:8px 14px;font-weight:600;cursor:pointer}
button.secondary{background:var(--line);color:var(--ink)}form{display:inline}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}input[type=text],textarea{width:100%;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
pre{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;font-size:12px;max-height:260px;overflow:auto}
.who-wife{color:#B0418A}.who-husband{color:var(--green)}.who-roach{color:var(--roach)}h2{font-size:17px;margin:22px 0 8px}
.job{padding:10px 14px;border-radius:10px;background:#FBEBC7;color:#5A3D00;margin-bottom:16px}
"""


def page(title, body, refresh=False):
    meta = '<meta http-equiv="refresh" content="3">' if refresh else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>{meta}<style>{CSS}</style></head><body>
<header><h1>🪳 The Roach Runs This House — Studio</h1><a href="/">Episodes</a><a href="/characters">Characters</a>
<a href="/new">+ New episode</a></header><main>{_job_banner()}{body}</main></body></html>"""


def _job_banner():
    if JOB["running"]:
        return f'<div class="job">⏳ Working: {html.escape(JOB["name"])} — page refreshes automatically<pre>{html.escape(chr(10).join(JOB["log"][-8:]))}</pre></div>'
    if JOB["error"]:
        return f'<div class="job" style="background:#F8D7D3;color:#8A2219">❌ {html.escape(JOB["name"])} failed<pre>{html.escape(JOB["error"][-1500:])}</pre></div>'
    if JOB["finished"]:
        return f'<div class="job" style="background:#D9F2DC;color:#1E5E28">✅ {html.escape(JOB["name"])} finished {html.escape(JOB["finished"])}</div>'
    return ""


def run_job(name, fn):
    with LOCK:
        if JOB["running"]:
            return False
        JOB.update(name=name, log=[], running=True, error=None, finished=None)

    def work():
        try:
            fn(lambda m: JOB["log"].append(str(m)))
            JOB["finished"] = time.strftime("%H:%M:%S")
        except Exception:
            JOB["error"] = traceback.format_exc()
        finally:
            JOB["running"] = False
    threading.Thread(target=work, daemon=True).start()
    return True


def esc(s):
    return html.escape(str(s if s is not None else ""))


def index():
    cards = []
    for d in pipeline.all_episodes():
        try:
            s = pipeline.status(d)
        except Exception as e:  # show broken files instead of crashing
            cards.append(f'<div class="card"><h3>{esc(d.name)}</h3><p class="pill failed">error</p><pre>{esc(e)}</pre></div>')
            continue
        bars = "".join(f'<div class="st {v["state"]}" title="{k}: {v["state"]}"></div>' for k, v in s["stages"].items())
        nxt = next((k for k, v in s["stages"].items() if v["state"] != "done"), "complete")
        cards.append(f"""<a href="/ep/{esc(s['id'])}" style="color:inherit;text-decoration:none"><div class="card">
<div class="id">{esc(s['id'])}</div><h3>{esc(s['title'])}</h3><div class="stages">{bars}</div>
<div class="muted">{int(s['progress'] * 100)}% · next: {esc(nxt.replace('_', ' '))}</div>
<p style="margin:8px 0 0">{esc(s['logline'])[:160]}</p></div></a>""")
    legend = '<p class="muted">Pipeline: ' + " → ".join(s.replace("_", " ") for s in config.STAGES) + "</p>"
    return page("Episodes", f"<h2>Season episodes</h2>{legend}<div class='grid'>{''.join(cards)}</div>", JOB["running"])


def episode_page(ep_id):
    d = pipeline.find(ep_id)
    ep = episode.load(d)
    s = pipeline.status(d)
    rd = pipeline.render_dir(d, ep["id"])
    man = json.loads((rd / "manifest.json").read_text()) if (rd / "manifest.json").exists() else None
    stages = "".join(f'<tr><td>{esc(k.replace("_", " "))}</td><td><span class="pill {v["state"]}">{esc(v["state"])}</span></td>'
                     f'<td class="muted">{esc(v["note"])}</td></tr>' for k, v in s["stages"].items())
    video = ""
    if man and (rd / man["video"]).exists():
        rel = (rd / man["video"]).relative_to(config.ROOT)
        video = f'<video controls playsinline preload="metadata" poster="/media/{esc((rd / "cover.jpg").relative_to(config.ROOT))}" src="/media/{esc(rel)}"></video>'
    else:
        video = '<div class="card muted">Not rendered yet.</div>'
    script_rows = []
    for sh in ep.get("shots") or []:
        lines = "".join(f'<div><b class="who-{esc(l["who"])}">{esc(l["who"].upper())}</b>: {esc(l["text"])}</div>'
                        for l in sh.get("lines") or [])
        sfx = ", ".join(x["name"] for x in sh.get("sfx") or [])
        script_rows.append(f"<tr><td><b>{esc(sh.get('id'))}</b><br><span class='muted'>{esc(sh.get('dur'))}s</span></td>"
                           f"<td>{esc(', '.join(sh.get('actors') or {}))}<br><span class='muted'>{esc(sh.get('background'))}</span></td>"
                           f"<td>{lines or '<span class=muted>(no dialogue)</span>'}<div class='muted'>sfx: {esc(sfx)}</div></td></tr>")
    outline = f"<pre>{esc(ep.get('outline'))}</pre>" if ep.get("outline") else ""
    missing = pipeline.missing_assets(d)
    miss_html = "<p class='pill done'>nothing missing</p>" if not missing else "<ul>" + "".join(f"<li>{esc(m)}</li>" for m in missing) + "</ul>"
    qc_html = ""
    if (rd / "qc_report.json").exists():
        q = json.loads((rd / "qc_report.json").read_text())
        rows = "".join(f'<tr><td>{esc(c["check"])}</td><td><span class="pill {c["status"]}">{c["status"]}</span></td><td class="muted">{esc(c["detail"])}</td></tr>' for c in q["checks"])
        qc_html = f"<h2>Quality control — {'PASSED' if q['passed'] else 'FAILED'} <span class='muted'>({esc(q['checked_at'])})</span></h2><table>{rows}</table>"
    can_approve = s["stages"]["quality_check"]["state"] == "done" and s["stages"]["approval"]["state"] != "done"
    approve_form = ""
    if can_approve:
        boxes = "".join(f'<label style="display:block"><input type="checkbox" name="c{i}" value="1"> {esc(h)}</label>' for i, h in enumerate(qc.HUMAN_REVIEW))
        approve_form = f"""<h2>Approve this cut</h2><div class="card"><form method="post" action="/ep/{esc(ep['id'])}/approve">
{boxes}<p><input type="text" name="reviewer" placeholder="Your name" required></p><p><textarea name="notes" placeholder="Notes (optional)"></textarea></p>
<button>Approve (does not publish)</button></form></div>"""
    ex = pipeline.export_dir(d)
    reels = ""
    if (ex / "post.txt").exists():
        reels = f"<h2>Facebook Reels package (not posted)</h2><div class='card'><p class='muted'>{esc(ex.relative_to(config.ROOT))}</p><pre>{esc((ex / 'post.txt').read_text())}</pre></div>"
    contact = f'<h2>Contact sheet</h2><img class="sheet" src="/media/{esc((rd / "contact_sheet.jpg").relative_to(config.ROOT))}">' if (rd / "contact_sheet.jpg").exists() else ""
    actions = f"""<div class="actions">
<form method="post" action="/ep/{esc(ep['id'])}/preview"><button class="secondary">Quick preview</button></form>
<form method="post" action="/ep/{esc(ep['id'])}/produce"><button>Render + QC</button></form>
<form method="post" action="/ep/{esc(ep['id'])}/qc"><button class="secondary">Re-run QC</button></form>
{'<form method="post" action="/ep/' + esc(ep['id']) + '/export"><button>Build export package</button></form>' if s['stages']['approval']['state'] == 'done' else ''}
</div>"""
    body = f"""<div class="id">{esc(ep['id'])}</div><h2 style="font-size:24px;margin-top:0">{esc(ep['title'])}</h2>
<p>{esc(ep.get('logline'))}</p><p class="muted"><b>Hook:</b> {esc(ep.get('hook'))}<br><b>Punchline:</b> {esc(ep.get('punchline'))}</p>
{actions}<div class="cols"><div>{video}</div><div><table>{stages}</table><h2>Missing assets</h2>{miss_html}</div></div>
{approve_form}{reels}{qc_html}<h2>Script &amp; shots</h2>{outline}<table><tr><th>Shot</th><th>Cast / set</th><th>Dialogue &amp; sound</th></tr>{''.join(script_rows)}</table>
{contact}<p class="muted">Edit <code>{esc(s['dir'])}/episode.yaml</code> to change the script, then Render + QC.</p>"""
    return page(ep["title"], body, JOB["running"])


def characters_page():
    from . import rigs
    b = rigs.bible()
    sheet = config.CHARACTERS_DIR / "model_sheet.png"
    status = "APPROVED" if b.get("approved") else "DRAFT — not yet matched to your reference image"
    rows = "".join(f"<tr><td><b>{esc(b[n]['display_name'])}</b></td><td>{esc(b[n]['personality'])}</td>"
                   f"<td>{''.join(f'<span title={esc(k)} style=display:inline-block;width:18px;height:18px;border-radius:4px;margin:1px;background:{esc(v)}></span>' for k, v in b[n]['palette'].items())}</td></tr>"
                   for n in ("wife", "husband", "roach"))
    refs = sorted(p.name for p in (config.CHARACTERS_DIR / "reference").glob("*") if p.name != ".gitkeep") if (config.CHARACTERS_DIR / "reference").exists() else []
    img = f'<img class="sheet" style="background:#fff" src="/media/{esc(sheet.relative_to(config.ROOT))}">' if sheet.exists() else "<p>Run <code>python -m studio sheet</code>.</p>"
    body = f"""<h2>Characters — {esc(status)}</h2><table>{rows}</table>
<p class="muted">Reference images in <code>assets/characters/reference/</code>: {esc(', '.join(refs) or 'none yet')}</p>
<form method="post" action="/sheet"><button class="secondary">Re-draw model sheet</button></form><h2>Model sheet</h2>{img}"""
    return page("Characters", body, JOB["running"])


def new_page(msg=""):
    body = f"""<h2>New episode</h2>{f'<p class="pill failed">{esc(msg)}</p>' if msg else ''}<div class="card"><form method="post" action="/new">
<p><input type="text" name="title" placeholder="Title, e.g. The Midnight Snack" required></p>
<p><input type="text" name="season" value="1"></p>
<p><textarea name="logline" placeholder="Logline (one sentence)"></textarea></p>
<p><textarea name="hook" placeholder="Hook (first 2 seconds)"></textarea></p>
<p><textarea name="punchline" placeholder="Punchline"></textarea></p><button>Create production folder</button></form></div>"""
    return page("New episode", body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _redirect(self, to):
        self.send_response(303)
        self.send_header("Location", to)
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/":
                return self._send(200, index())
            if path == "/characters":
                return self._send(200, characters_page())
            if path == "/new":
                return self._send(200, new_page())
            if path.startswith("/ep/"):
                return self._send(200, episode_page(urllib.parse.unquote(path[4:])))
            if path == "/api/status":
                data = [pipeline.status(d) for d in pipeline.all_episodes()]
                return self._send(200, json.dumps(data, indent=2), "application/json")
            if path.startswith("/media/"):
                return self._media(urllib.parse.unquote(path[7:]))
            return self._send(404, page("Not found", "<p>Not found.</p>"))
        except FileNotFoundError as e:
            return self._send(404, page("Not found", f"<pre>{esc(e)}</pre>"))
        except Exception:
            return self._send(500, page("Error", f"<pre>{esc(traceback.format_exc())}</pre>"))

    def _media(self, rel):
        f = (config.ROOT / rel).resolve()
        if not any(str(f).startswith(str(r.resolve()) + "/") for r in MEDIA_ROOTS) or not f.is_file():
            return self._send(404, "not found", "text/plain")
        size = f.stat().st_size
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else 0
            end = min(int(b) if b else size - 1, size - 1)
            with open(f, "rb") as fh:
                fh.seek(start)
                data = fh.read(end - start + 1)
            return self._send(206, data, ctype, {"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes"})
        return self._send(200, f.read_bytes(), ctype, {"Accept-Ranges": "bytes"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0) or 0)
        form = urllib.parse.parse_qs(self.rfile.read(n).decode()) if n else {}
        get = lambda k, d="": form.get(k, [d])[0]
        try:
            if path == "/new":
                try:
                    d = pipeline.new_episode(get("title").strip(), int(get("season", "1") or 1), None, get("logline"), get("hook"), get("punchline"))
                except (FileExistsError, ValueError) as e:
                    return self._send(400, new_page(str(e)))
                ep = episode.load(d)
                return self._redirect(f"/ep/{ep['id']}")
            if path == "/sheet":
                from . import sheet
                run_job("model sheet", lambda log: log(sheet.model_sheet()))
                return self._redirect("/characters")
            if path.startswith("/ep/"):
                ep_id, _, action = path[4:].rpartition("/")
                d = pipeline.find(urllib.parse.unquote(ep_id))
                from . import render
                if action in ("produce", "preview"):
                    def work(log, d=d, preview=(action == "preview")):
                        render.render_episode(d, preview=preview, log=log)
                        if not preview:
                            r = qc.run_qc(d)
                            log(f"QC {'PASSED' if r.passed else 'FAILED'}")
                    run_job(f"{action} {ep_id}", work)
                elif action == "qc":
                    run_job(f"QC {ep_id}", lambda log: log("passed" if qc.run_qc(d).passed else "failed"))
                elif action == "approve":
                    conf = [get(f"c{i}") == "1" for i in range(len(qc.HUMAN_REVIEW))]
                    try:
                        pipeline.approve(d, get("reviewer"), conf, get("notes"))
                    except pipeline.GateError as e:
                        return self._send(400, page("Not approved", f"<p class='pill failed'>{esc(e)}</p><p><a href='/ep/{esc(ep_id)}'>Back</a></p>"))
                elif action == "export":
                    run_job(f"export {ep_id}", lambda log: log(pipeline.export(d)))
                return self._redirect(f"/ep/{urllib.parse.quote(ep_id)}")
            return self._send(404, "not found", "text/plain")
        except Exception:
            return self._send(500, page("Error", f"<pre>{esc(traceback.format_exc())}</pre>"))


def make_server(host="127.0.0.1", port=8765):
    return ThreadingHTTPServer((host, port), Handler)


def serve(host="127.0.0.1", port=8765):
    srv = make_server(host, port)
    print(f"Studio dashboard running at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
