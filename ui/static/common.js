// Shared by the game (game.html) and the test bench (bench.html): API calls,
// formatting, the box score and "Watch it" (drive-by-drive playback, task 3.1).

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
// Q1-Q4, then OT, 2OT, ... (a playoff game plays overtime periods until someone scores, G6).
const quarterText = q => q <= 4 ? "Q" + q : q === 5 ? "OT" : `${q - 4}OT`;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const money = n => n == null ? "" : `$${Number(n).toFixed(2)}M`;
const POSITIONS = ["QB", "RB", "WR", "TE", "OL", "DL", "LB", "CB", "S", "K", "P"];

async function call(url, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok) throw data;
  return data;
}
function toast(msg, kind = "good") {
  const t = $("#toast"); t.textContent = msg; t.className = kind;
  clearTimeout(t._h); t._h = setTimeout(() => t.className = "", 4200);
}
const fail = e => toast(e?.error || e?.message || String(e), "bad");

// ---- Football formatting ------------------------------------------------
const clockText = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
const QUARTERS = { 1: "1st quarter", 2: "2nd quarter", 3: "3rd quarter", 4: "4th quarter", 5: "Overtime" };
const ORD = ["", "1st", "2nd", "3rd", "4th"];
const RESULT_LABEL = { touchdown: "Touchdown", field_goal: "Field goal", field_goal_missed: "Missed FG", punt: "Punt",
  interception: "Interception", fumble: "Fumble", turnover_on_downs: "Downs", safety: "Safety",
  end_of_half: "End of half", end_of_game: "End of game" };
const spotOf = (team, other, y) => y === 50 ? "50" : y < 50 ? `${team} ${y}` : `${other} ${100 - y}`;
const playClassOf = p => p.result === "touchdown" ? "td"
  : ["interception", "fumble", "turnover_on_downs", "safety", "field_goal_missed"].includes(p.result) ? "to" : "";
const togoText = p => p.distance >= 100 - p.yardline ? "goal" : p.distance;

function driveTable(b, drives, ourTeam) {
  const h = b.game.home_team_id, a = b.game.away_team_id, other = t => t === h ? a : h;
  if (!drives.length) return `<p class="empty">No drives finished yet.</p>`;
  return `<table class="drives"><tr><th>#</th><th>Team</th><th>Start</th><th>From</th><th class="num">Plays</th>
    <th class="num">Yds</th><th class="num">Time</th><th>Result</th><th class="num">${a}-${h}</th></tr>
    ${drives.map(d => `<tr class="${d.team === ourTeam ? "ours" : ""}"><td>${d.number}</td><td>${d.team}</td>
      <td>${quarterText(d.quarter)} ${clockText(d.clock)}</td><td>${spotOf(d.team, other(d.team), d.start_yardline)}</td>
      <td class="num">${d.plays}</td><td class="num">${d.yards}</td><td class="num">${clockText(d.seconds)}</td>
      <td class="how">${["touchdown", "field_goal", "safety"].includes(d.result) ? `<b>${RESULT_LABEL[d.result]}</b>` : RESULT_LABEL[d.result] || d.result}</td>
      <td class="num">${d.away_score}-${d.home_score}</td></tr>`).join("")}</table>`;
}

// ---- Box score ------------------------------------------------------------
function boxScoreHtml(b, ourTeam) {
  const g = b.game, h = g.home_team_id, a = g.away_team_id;
  const scoreline = `<div class="scoreline">${a} ${g.away_score} &nbsp;at&nbsp; ${h} ${g.home_score}</div>`;
  if (!b.simulated) return scoreline + `<p class="empty">This score was entered by hand, so there's no play-by-play.</p>`;
  const row = (label, f) => `<tr><td>${label}</td><td class="num">${f(b.teams[a])}</td><td class="num">${f(b.teams[h])}</td></tr>`;
  const lead = (stat, fmt) => {
    const best = team => b.players.filter(p => p.team_id === team && p[stat]).sort((x, y) => y[stat] - x[stat])[0];
    return [a, h].map(t => { const p = best(t); return p ? `${t} ${esc(p.name)}: ${fmt(p)}` : `${t}: none`; }).join("<br>");
  };
  let quarter = 0, pbp = "";
  for (const p of b.plays) {
    if (p.quarter !== quarter) { quarter = p.quarter; pbp += `<div class="q">${QUARTERS[quarter]}</div>`; }
    const spot = p.yardline === 50 ? "50" : p.yardline < 50 ? `own ${p.yardline}` : `opp ${100 - p.yardline}`;
    pbp += `<div class="play ${playClassOf(p)}"><span class="sit">${clockText(p.clock)}</span><span class="sit">${p.offense_team_id} · ${ORD[p.down]} & ${togoText(p)}<br>${spot}</span>
      <span>${esc(p.text)} <span class="pos">${p.call.replace(/_/g, " ")}${p.defense_call ? " vs " + p.defense_call.replace(/_/g, " ") : ""}</span></span>
      <span class="sit num">${a} ${p.away_score}-${p.home_score}</span></div>`;
  }
  return `${scoreline}<div class="grid">
      <table><tr><th>Team</th><th class="num">${a}</th><th class="num">${h}</th></tr>
        ${row("Total yards", t => t.total_yds)}${row("Passing", t => `${t.pass_cmp}/${t.pass_att}, ${t.pass_yds}`)}
        ${row("Rushing", t => `${t.rush_att}-${t.rush_yds}`)}${row("First downs", t => t.first_downs)}
        ${row("Sacked", t => t.sacked)}${row("Turnovers", t => t.turnovers)}${row("Field goals", t => `${t.fg_made}/${t.fg_att}`)}${row("Punts", t => t.punts)}</table>
      <div class="leaders">
        <div><b>Passing</b>${lead("pass_yds", p => `${p.pass_cmp}/${p.pass_att}, ${p.pass_yds} yds, ${p.pass_td || 0} TD, ${p.int_thrown || 0} INT`)}</div>
        <div><b>Rushing</b>${lead("rush_yds", p => `${p.rush_att} for ${p.rush_yds} yds, ${p.rush_td || 0} TD`)}</div>
        <div><b>Receiving</b>${lead("rec_yds", p => `${p.rec} for ${p.rec_yds} yds, ${p.rec_td || 0} TD`)}</div>
        <div><b>Sacks</b>${lead("def_sacks", p => `${p.def_sacks}`)}<b style="margin-top:6px">Interceptions</b>${lead("def_int", p => `${p.def_int}`)}</div>
      </div></div>
    <h3>Drives <span class="sub">${b.drives.length} possessions</span></h3>
    <div class="scroll">${driveTable(b, b.drives, ourTeam)}</div>
    <h3>Play by play <span class="sub">${b.plays.length} plays · green: touchdowns · red: turnovers</span></h3>
    <div class="pbp">${pbp}</div>`;
}

// ---- The scoreboard and the field (Watch it and Call it) -------------------
// The home team drives left to right; each end zone is 10 of the 120 yards drawn.
function boardHtml(away, home, awayScore, homeScore, poss, status, sub) {
  return `<div class="board">
    <div class="side ${poss === away ? "poss" : ""}"><span class="pts">${awayScore}</span><span class="abbr">${away}</span></div>
    <div class="mid"><b>${status}</b><span>${sub}</span></div>
    <div class="side home ${poss === home ? "poss" : ""}"><span class="abbr">${home}</span><span class="pts">${homeScore}</span></div>
  </div>`;
}
function fieldHtml(home, away, ball = null) {
  // ball: { poss, yardline, distance, driveTeam, driveStart } or null when the game is over
  const abs = (team, y) => team === home ? y : 100 - y;
  const x = yard => `${(10 + yard) / 120 * 100}%`;
  const other = t => t === home ? away : home;
  let field = `<div class="ez" style="left:0">${esc(home)}</div><div class="ez" style="right:0">${esc(away)}</div>`;
  for (let yd = 10; yd <= 90; yd += 10) field += `<div class="yl" style="left:${x(yd)}"><span>${yd <= 50 ? yd : 100 - yd}</span></div>`;
  if (ball) {
    const at = abs(ball.poss, ball.yardline), from = abs(ball.driveTeam, ball.driveStart);
    field += `<div class="run" style="left:${x(Math.min(at, from))};width:${Math.abs(at - from) / 120 * 100}%"></div>`;
    if (ball.distance < 100 - ball.yardline) field += `<div class="togo" style="left:${x(abs(ball.poss, ball.yardline + ball.distance))}"></div>`;
    field += `<div class="ball" style="left:${x(at)}" title="${ball.poss} ball"></div>`;
  }
  const label = ball ? `Ball at ${spotOf(ball.poss, other(ball.poss), ball.yardline)}` : "Game over";
  return `<div class="field" role="img" aria-label="${label}">${field}</div>`;
}

// ---- Watch it: drive-by-drive playback of a simulated game ----------------
// new WatchView(element, boxScore, { ourTeam, onEnd }) renders into the element and
// owns its buttons. onEnd runs once, the first time the last play is shown.
class WatchView {
  constructor(el, box, { ourTeam = null, onEnd = null } = {}) {
    this.el = el; this.b = box; this.ourTeam = ourTeam; this.onEnd = onEnd;
    this.idx = 0; this.timer = null; this.ended = false;
    el.onclick = e => { const w = e.target.closest("[data-w]"); if (w) this.move(w.dataset.w); };
    this.render();
  }
  stop() { if (this.timer) { clearInterval(this.timer); this.timer = null; } }
  move(how) {
    const n = this.b.plays.length;
    if (how === "auto") {
      if (this.timer) { this.stop(); return this.render(); }
      this.timer = setInterval(() => { this.idx = Math.min(n, this.idx + 1); if (this.idx >= n) this.stop(); this.render(); }, 900);
    } else {
      this.stop();
      if (how === "play") this.idx = Math.min(n, this.idx + 1);
      else if (how === "end") this.idx = n;
      else if (how === "restart") this.idx = 0;
      else if (how === "drive") {
        const next = this.b.plays[this.idx];
        const d = next && this.b.drives.find(d => d.first_play <= next.n && next.n <= d.last_play);
        this.idx = d ? d.last_play : n;
      }
    }
    this.render();
  }
  render() {
    const { b, idx } = this, g = b.game, h = g.home_team_id, a = g.away_team_id, P = b.plays, n = P.length;
    const other = t => t === h ? a : h;
    const done = idx >= n, last = idx ? P[idx - 1] : null, next = done ? null : P[idx];
    const score = last ? [last.away_score, last.home_score] : [0, 0];
    const drive = next && b.drives.find(d => d.first_play <= next.n && next.n <= d.last_play);
    const poss = next?.offense_team_id;

    let status, sub;
    if (done) { status = P[n - 1].quarter >= 5 ? `Final (${quarterText(P[n - 1].quarter)})` : "Final"; sub = `${n} plays · ${b.drives.length} drives`; }
    else {
      status = `${quarterText(next.quarter)} ${clockText(next.clock)}`;
      sub = `${poss} ball · ${ORD[next.down]} & ${togoText(next)} at ${spotOf(poss, other(poss), next.yardline)}`;
    }
    const ball = next && { poss, yardline: next.yardline, distance: next.distance, driveTeam: drive.team, driveStart: drive.start_yardline };
    const lastText = last ? `<span class="sit">${last.offense_team_id} · ${quarterText(last.quarter)} ${clockText(last.clock)}</span> ${esc(last.text)}`
      : `<span class="sit">Kickoff.</span> ${esc(poss)} receives.`;
    const thisDrive = drive ? P.slice(drive.first_play - 1, idx) : [];
    const finished = b.drives.filter(d => d.last_play <= idx);
    this.el.innerHTML = `
      ${boardHtml(a, h, score[0], score[1], poss, status, sub)}
      ${fieldHtml(h, a, ball)}
      <div class="lastplay ${last ? playClassOf(last) : ""}">${lastText}</div>
      <div class="row">
        <button class="btn" data-w="play" ${done ? "disabled" : ""}>Next play</button>
        <button class="btn primary" data-w="drive" ${done ? "disabled" : ""}>Next drive</button>
        <button class="btn" data-w="auto" ${done ? "disabled" : ""}>${this.timer ? "Pause" : "Autoplay"}</button>
        <button class="btn" data-w="end" ${done ? "disabled" : ""}>Skip to the end</button>
        <button class="btn" data-w="restart" ${idx ? "" : "disabled"}>Restart</button>
        <span class="note">Play ${idx} of ${n}</span>
      </div>
      <div class="grid">
        <div><h3>${drive ? `This drive <span class="sub">${drive.team} from ${spotOf(drive.team, other(drive.team), drive.start_yardline)}</span>` : "This drive"}</h3>
          <div class="drive-now">${thisDrive.length ? thisDrive.map(p => `<div><span class="sit">${ORD[p.down]} & ${togoText(p)}</span> ${esc(p.text)}</div>`).join("")
            : `<p class="empty">${done ? "The game is over." : "No snaps yet on this drive."}</p>`}</div></div>
        <div><h3>Drives <span class="sub">${finished.length} finished</span></h3><div class="scroll" style="max-height:260px">${driveTable(b, finished, this.ourTeam)}</div></div>
      </div>`;
    if (done && !this.ended) { this.ended = true; this.onEnd?.(); }
  }
}

// ---- The agents' reports (0.2, 1.3) and the GM's team (1.4) ------------------------
const REPORT_LABELS = { answer: "Answer", recommendation: "Recommendation", weakest_area: "Weakest area",
  target_profile: "Target profile", evidence: "Evidence", fits_under_cap: "Fits under the cap",
  salary_to_clear: "Salary to clear", payroll: "Payroll (from the league)", cap_space: "Cap space (from the league)" };
const MONEY_FIELDS = ["payroll", "cap_space", "salary_to_clear"];

function reportHtml(rep) {
  if (!rep || typeof rep !== "object") return `<pre>${esc(rep ?? "")}</pre>`;
  const value = (k, v) => Array.isArray(v) ? `<ul>${v.map(e => `<li>${esc(e)}</li>`).join("")}</ul>`
    : typeof v === "boolean" ? (v ? "Yes" : "No") : MONEY_FIELDS.includes(k) ? money(v) : esc(v);
  return `<dl class="report">${Object.entries(rep).filter(([k]) => k !== "team_id").map(([k, v]) =>
    `<dt>${REPORT_LABELS[k] || esc(k)}${k === "answer" && rep.team_id ? ` <span class="pos">${esc(rep.team_id)}</span>` : ""}</dt>
     <dd>${value(k, v)}</dd>`).join("")}</dl>`;
}
function toolCallsHtml(calls) {
  if (!calls.length) return `<p class="empty">No tool calls.</p>`;
  return calls.map((c, i) => {
    let body = c.result; try { body = JSON.stringify(JSON.parse(c.result), null, 2); } catch {}
    return `<details class="call"><summary>${i + 1}. ${esc(c.tool)}(${esc(JSON.stringify(c.args))}) ${c.error ? `<span class="badge bad">error</span>` : ""}</summary><pre>${esc(body)}</pre></details>`;
  }).join("");
}
function runStatsHtml(r) {
  const calls = r.tool_calls ? r.tool_calls.length : r.specialists.reduce((n, s) => n + s.tool_calls.length, 0);
  return `<span>${r.seconds}s</span>${r.delegations ? `<span>${r.delegations.length} delegations</span>` : ""}<span>${calls} tool calls</span>
    ${r.input_tokens != null ? `<span>${r.input_tokens} in / ${r.output_tokens} out tokens</span>` : ""}
    ${r.cost != null ? `<span>$${Number(r.cost).toFixed(4)}</span>` : ""}<span>${esc(r.model || "")}</span>`;
}
// Who the GM asked, the task it wrote for each, what each specialist said and, with
// `withTools`, the raw tool calls behind it (the bench shows them; the game doesn't).
const memberKey = s => String(s || "").toLowerCase().replace(/[^a-z]/g, "");
function frontOfficeHtml(r, withTools = false) {
  if (!r.specialists.length) return `<p class="empty">The GM answered without asking a specialist.</p>`;
  const tasks = r.delegations.slice();
  return r.specialists.map(s => {
    const i = tasks.findIndex(d => memberKey(d.member) === memberKey(s.name));
    const task = i >= 0 ? tasks.splice(i, 1)[0].task : null;
    const tools = s.tool_calls.map(c => c.tool).join(", ") || "no tools";
    return `<details class="specialist"><summary><b>${esc(s.name)}</b> <span class="note">${s.tool_calls.length} tool calls: ${esc(tools)}</span></summary>
      ${task ? `<p class="task"><span class="note">The GM asked:</span> ${esc(task)}</p>` : ""}
      ${reportHtml(s.report)}${withTools ? `<h3>Tool calls</h3>${toolCallsHtml(s.tool_calls)}` : ""}</details>`;
  }).join("");
}
