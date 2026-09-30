// Run a built page's script against a minimal DOM, hand it a set of threads, and print
// what the page made of them.
//
//   node inpage.js <index.html> <threads.json>
//
// Prints JSON: { orphans: [thread id, ...], anchored: [thread id, ...] }.
//
// The page decides whether a thread belongs to a line by comparing the commit recorded on
// the thread against the commits it was built with. That comparison is not reachable from
// outside the script, so this drives the observable end of it instead: a thread the page
// cannot place goes into the orphan list, under a heading saying the commit is not part of
// this diff. Which is the thing that goes wrong, and the thing worth asserting on.
const fs = require("fs");

// Enough of a selector engine for the ones the page uses: a descendant chain of
// tag/.class/[attr] compounds. Returning [] from querySelectorAll, as this did, meant
// paintThreads walked an empty document and every case about it passed without it having
// drawn anything. It is the function that runs every four seconds and the one two review
// rounds have found bugs in, so it is worth being able to see.
// A class can arrive two ways: el() sets className, and the page calls classList.add.
// Reading only the first made a row marked by classList invisible both to the page's own
// querySelectorAll and to what this reports.
const classesOf = (node) => [
  ...String(node.className || "").split(" ").filter(Boolean),
  ...(node.classList && node.classList._s ? [...node.classList._s] : []),
];

const matchesOne = (node, sel) => {
  const tag = (sel.match(/^[a-zA-Z]+/) || [])[0];
  if (tag && node.tagName !== tag.toUpperCase()) return false;
  const have = classesOf(node);
  if (![...sel.matchAll(/\.([\w-]+)/g)].every((m) => have.includes(m[1]))) return false;
  return [...sel.matchAll(/\[([\w-]+)(?:=["']?([^\]"']*)["']?)?\]/g)].every(([, name, want]) => {
    const key = name.startsWith("data-")
      ? name.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())
      : name;
    const got = name.startsWith("data-") ? (node.dataset || {})[key] : node[name];
    return want === undefined ? got !== undefined : String(got) === want;
  });
};

const descendants = (node, out = []) => {
  (node.children || []).forEach((c) => { out.push(c); descendants(c, out); });
  return out;
};

const queryAll = (root, selector) =>
  selector.split(",").flatMap((one) => {
    const parts = one.trim().split(/\s+/);
    const last = parts[parts.length - 1];
    return descendants(root).filter((node) => {
      if (!matchesOne(node, last)) return false;
      let up = node.parentNode;
      for (let i = parts.length - 2; i >= 0; i--) {
        while (up && up !== root && !matchesOne(up, parts[i])) up = up.parentNode;
        if (!up || up === root) return matchesOne(root, parts[i]) && i === 0;
        up = up.parentNode;
      }
      return true;
    });
  });

const mk = (tag) => {
  const node = {
    tagName: (tag || "div").toUpperCase(),
    children: [],
    dataset: new Proxy({}, { set(target, key, value) { target[key] = String(value); return true; } }),
    style: {},
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); },
      remove(c) { this._s.delete(c); },
      toggle(c, on) { on === undefined ? (this._s.has(c) ? this._s.delete(c) : this._s.add(c)) : (on ? this._s.add(c) : this._s.delete(c)); },
      contains(c) { return this._s.has(c); },
    },
    appendChild(c) { c.parentNode = node; node.children.push(c); return c; },
    replaceChildren(...kids) { node.children = []; kids.forEach((k) => node.appendChild(k)); },
    remove() {
      const p = node.parentNode;
      if (p) { const i = p.children.indexOf(node); if (i >= 0) p.children.splice(i, 1); }
    },
    after(sib) {
      const p = node.parentNode;
      if (!p) return;
      p.children.splice(p.children.indexOf(node) + 1, 0, sib);
      sib.parentNode = p;
    },
    addEventListener(type, fn) { (node._on = node._on || {})[type] = fn; },
    focus() {},
    closest(sel) {
      for (let up = node; up; up = up.parentNode) if (matchesOne(up, sel)) return up;
      return null;
    },
    setAttribute(k, v) { node[k] = v; }, getAttribute(k) { return node[k]; },
    matches() { return false; },
    querySelectorAll(sel) { return queryAll(node, sel); },
    querySelector(sel) { return queryAll(node, sel)[0] || null; },
    scrollIntoView() {},
  };
  return node;
};

// Handlers the page puts on the document itself. The click that opens a question is one
// of them, so a case cannot reach it without these being kept.
const docHandlers = {};
const registry = {};
const node = (id) => (registry[id] = registry[id] || mk("div"));
const nest = (parent, kids) => kids.forEach((id) => node(parent).appendChild(node(id)));
globalThis.document = {
  title: "",
  body: mk("body"),
  createElement: mk,
  createTextNode: (t) => ({ nodeValue: t }),
  getElementById: node,
  querySelectorAll: () => [],
  addEventListener: (type, fn) => { docHandlers[type] = fn; },
  hidden: false,
};
nest("board", ["pane", "side"]);
nest("filesView", ["stageRail", "filePane"]);
nest("filePane", ["fileGroups"]);
// Both carry the hidden attribute in the page, so they start hidden as they really do.
node("side").hidden = true;
node("filesView").hidden = true;

// The reviewed ticks live in localStorage, keyed by sha, so a case can seed them.
const stored = process.argv[4] ? fs.readFileSync(process.argv[4], "utf8") || null : null;
globalThis.localStorage = { getItem: () => stored, setItem: () => {} };
// A drag that ends on a row is a selection, not a click, and the page checks for one
// before opening a thread. Nothing here selects anything.
globalThis.window = { confirm: () => false, location: { reload() {} }, getSelection: () => "" };
let poll = null;
// The page's own four second poll, kept so a case can make time pass on purpose.
globalThis.setInterval = (fn) => { poll = fn; return 0; };

const threads = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
// { anchor: "files a.py:2 del", question: "…" } — the row to click and what to type.
const plan = process.argv[5] ? JSON.parse(fs.readFileSync(process.argv[5], "utf8")) : null;
const posted = [];
let served = threads;
// The page reads its threads from /thread on the first poll, so that is where they go in.
globalThis.fetch = (url, init) => {
  if (String(url).startsWith("/thread")) {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ threads: served, revision: "", watcher: true }),
    });
  }
  if (String(url) === "/ask") {
    posted.push(JSON.parse((init || {}).body || "{}"));
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
  }
  if (String(url) === "/reply" || String(url) === "/resolve") {
    posted.push({ url, ...JSON.parse((init || {}).body || "{}") });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
  }
  return Promise.reject(new Error("only /thread and /ask are served here"));
};

const html = fs.readFileSync(process.argv[2], "utf8");
const script = html.split("<script>")[1].split("</script>").slice(0, -1).join("</script>");

try {
  new Function(script)();
} catch (error) {
  console.error(`page script threw: ${error.constructor.name}: ${error.message}`);
  process.exit(1);
}

// Every reply box on the page, wherever it was drawn, with the thread it answers. The
// panel, the orphan list and the sections hang off their own registry nodes, so a search
// from the boards alone would miss them.
const replyBoxes = () => {
  const out = [];
  const seen = new Set();
  const walk = (n, thread) => {
    if (seen.has(n)) return;
    seen.add(n);
    const id = (n.dataset || {}).thread || thread;
    if (n.tagName === "TEXTAREA" && id) out.push({ thread: id, input: n });
    (n.children || []).forEach((c) => walk(c, id));
  };
  [registry.board, registry.fileGroups, registry.sideBody, registry.orphanList,
   registry.commitThreadList].filter(Boolean).forEach((r) => walk(r, null));
  return out;
};

const anchorOf = (n) => {
  const d = n.dataset || {};
  return `${d.view || "commits"} ${d.file}:${d.line} ${d.side}`;
};

/* Drive the page the way a reviewer does, one step at a time. Every step runs through
   the page's own handlers, so anything the page will not do fails here too.

   Steps: {open} expand every file box, {gutter} click a line's number, {type} fill the
   composer, {send} press the button, {stage} click a rail entry, {whole} press "Show the
   whole file", {closeSide} press the panel's X, {tick} run the poll, {review} tick the
   file at that path as reviewed, {reply} type into the first reply box of the thread with
   that id, the way a reader does: focus, then text, {commit} click that commit on the
   rail, {showOnCommits} press the way to the Commits tab on a listed commit thread,
   {cancel} press the composer's Cancel, {key} press a key on the page, {ctrlEnterTwice}
   send the composer twice from the keyboard, {replyEnterTwice} the same in a reply box,
   {yes} press "Yes, investigate", {tab} press a tab, {openFile} open a file by its path,
   {wholeOf} press "Show the whole file" under that file.

   A few milliseconds pass after each step, so a poll or a send can settle between two
   presses the way it does between a reader's clicks. */
async function drive(steps) {
  // getElementById hands out standalone nodes, so the page's subtrees hang off those
  // rather than off body. A search from body alone found nothing at all.
  const roots = () => [registry.fileGroups, registry.board, document.body].filter(Boolean);
  const all = (sel) => roots().flatMap((r) => queryAll(r, sel));
  const press = (n) => n && n._on && n._on.click && n._on.click();
  const done = [];
  for (const step of steps) {
    await new Promise((settle) => setTimeout(settle, 5));
    if (step.open) {
      all("button.file-head").forEach(press);
      done.push("open");
    } else if (step.gutter !== undefined) {
      const row = all("tr[data-line]").find((n) => anchorOf(n) === step.gutter);
      if (!row) return [...done, `no row anchored ${step.gutter}`];
      if (!docHandlers.click) return [...done, "the page registered no click handler"];
      docHandlers.click({ target: queryAll(row, "td.gut")[0] || row, preventDefault() {} });
      done.push(all("div.composer").length ? "composer" : "side");
    } else if (step.type !== undefined) {
      const input = all("div.composer").flatMap((c) => queryAll(c, "textarea"))[0];
      if (!input) return [...done, "no composer to type into"];
      input.value = step.type;
      done.push("typed");
    } else if (step.send) {
      const send = all("div.composer")
        .flatMap((c) => queryAll(c, "button.btn"))
        .find((b) => b.textContent === "Ask Claude");
      if (!send) return [...done, "no send button"];
      press(send);
      done.push("sent");
    } else if (step.stage !== undefined) {
      const btn = queryAll(registry.stageRail || mk("div"), "button.commit-btn")
        .find((b) => queryAll(b, "span.cb-head").some((h) => h.textContent === step.stage));
      if (!btn) return [...done, `no rail entry named ${step.stage}`];
      press(btn);
      done.push(`stage ${step.stage}`);
    } else if (step.whole) {
      const btn = all("button.wholefile")[0];
      if (!btn) return [...done, "no whole-file button"];
      press(btn);
      done.push("whole");
    } else if (step.closeSide) {
      press(registry.sideClose);
      done.push("closed");
    } else if (step.commit !== undefined) {
      const btn = (registry.commits ? registry.commits.children : [])[step.commit];
      if (!btn) return [...done, `no commit ${step.commit} on the rail`];
      press(btn);
      done.push(`commit ${step.commit}`);
    } else if (step.showOnCommits !== undefined) {
      const btn = queryAll(registry.commitThreadList || mk("div"), "button.showoncommits")
        .find((b) => b.dataset.thread === step.showOnCommits);
      if (!btn) return [...done, `no way to the commits tab from ${step.showOnCommits}`];
      press(btn);
      done.push(`to commits from ${step.showOnCommits}`);
    } else if (step.reply !== undefined) {
      const box = replyBoxes().find((b) => b.thread === step.reply.id);
      if (!box) return [...done, `no reply box on ${step.reply.id}`];
      const on = box.input._on || {};
      if (on.focus) on.focus();
      box.input.value = step.reply.text;
      done.push(`typing in ${step.reply.id}`);
    } else if (step.review !== undefined) {
      const bar = all("div.file-bar")
        .find((b) => queryAll(b, "span.fpath").some((n) => n.textContent === step.review));
      const box = bar && queryAll(bar, "input")[0];
      if (!box) return [...done, `no reviewed box on ${step.review}`];
      box.checked = true;
      box._on.change();
      done.push(`reviewed ${step.review}`);
    } else if (step.cancel) {
      const b = all("div.composer").flatMap((c) => queryAll(c, "button.btn")).find((b) => b.textContent === "Cancel");
      if (!b) return [...done, "no cancel"];
      press(b); done.push("cancelled");
    } else if (step.key !== undefined) {
      if (!docHandlers.keydown) return [...done, "no keydown"];
      docHandlers.keydown({ key: step.key, target: mk("div"), preventDefault() {} });
      done.push("key " + step.key);
    } else if (step.ctrlEnterTwice) {
      const input = all("div.composer").flatMap((c) => queryAll(c, "textarea"))[0];
      if (!input) return [...done, "no composer"];
      const ev = { key: "Enter", ctrlKey: true, preventDefault() {} };
      input._on.keydown(ev); input._on.keydown(ev);
      done.push("ctrl-enter x2");
    } else if (step.replyEnterTwice !== undefined) {
      const box = replyBoxes().find((b) => b.thread === step.replyEnterTwice);
      if (!box) return [...done, "no reply box"];
      const ev = { key: "Enter", ctrlKey: true, preventDefault() {} };
      box.input._on.keydown(ev); box.input._on.keydown(ev);
      done.push("reply ctrl-enter x2");
    } else if (step.yes !== undefined) {
      const b = [registry.board, registry.fileGroups, registry.sideBody, registry.orphanList,
        registry.commitThreadList].filter(Boolean)
        .flatMap((r) => queryAll(r, "button.btn")).find((n) => n.textContent === "Yes, investigate");
      if (!b) return [...done, "no yes button"];
      press(b); done.push("yes");
    } else if (step.tab !== undefined) {
      press(step.tab === "files" ? registry.tabFiles : registry.tabCommits);
      done.push("tab " + step.tab);
    } else if (step.openFile !== undefined) {
      const h = all("button.file-head").find((b) => queryAll(b, "span.fpath").some((n) => n.textContent === step.openFile));
      if (!h) return [...done, "no file " + step.openFile];
      press(h); done.push("opened " + step.openFile);
    } else if (step.wholeOf !== undefined) {
      const b = all("button.wholefile").find((n) => n.dataset.file === step.wholeOf);
      if (!b) return [...done, "no whole " + step.wholeOf];
      press(b); done.push("whole " + step.wholeOf);
    } else if (step.serve !== undefined) {
      served = step.serve;
      done.push(`serving ${served.length}`);
    } else if (step.tick) {
      if (!poll) return [...done, "the page registered no poll"];
      poll();
      done.push("tick");
    }
  }
  return done;
}

// The poll is a promise; let it settle before reading what it drew.
setTimeout(async () => {
  const text = (n) =>
    (n.children || []).length ? (n.children || []).map(text).join(" ") : (n.textContent || "");
  // An orphan card is identified by the anchor printed in its header, not by the thread
  // id, which the card never prints, and not by the question, which is a substring match:
  // a card for "Q10" contains "Q1", so one thread was reported orphaned because another
  // one was.
  const cards = (registry.orphanList ? registry.orphanList.children : []).map(text);
  // A files thread has no commit, so its card names only where the line was.
  const header = (t) =>
    t.view === "files"
      ? `${t.file || "?"}:${t.line || "?"}`
      : `${t.commit || "?"} · ${t.file || "?"}:${t.line || "?"}`;
  const orphans = threads
    .filter((t) => cards.some((card) => card.includes(header(t))))
    .map((t) => t.id);

  // A paint that throws is swallowed by refresh()'s catch into the status line, and every
  // case that only counts orphan cards then passes against a page that drew nothing at
  // all. The status is reported so a case can tell those apart.
  const asking = plan ? await drive(plan.steps || []) : null;


  // A step can be asynchronous — a send, or a poll that refetches — so the page is read
  // only once those have settled. Walking it straight after the steps reported the page
  // as it was before the last one landed.
  setTimeout(() => {
  // The rows a stage's pane actually drew. A pane is seeded from what survived and from
  // what the stage removed, and the removal half is only observable here: the data says a
  // line is gone, and whether the page puts it on screen is a separate question.
  //
  // Only inside the stage pane. The all-files view writes into the same container, so a
  // walk from the container would report its rows too and a case about one view would
  // pass on the strength of the other.
  const pane = [];
  // What a row on the files tab offers a question: the anchor it carries, and whether a
  // thread was drawn under it. Both are the point of the tab being askable at all, and
  // neither is visible in the row text.
  const anchors = [];
  const asked = [];
  const outdated = [];
  const gutter = [];
  const walk = (n, inside) => {
    const cls = classesOf(n).join(" ");
    if (n.tagName === "TR") {
      const d = n.dataset || {};
      const at = `${d.view || "commits"} ${d.file}:${d.line} ${d.side}`;
      if (d.line) anchors.push(at);
      // Whether the page matched a thread to this row. Set in both layouts, unlike the
      // inline thread row, which the docked panel replaces.
      if (d.line && d.asked) asked.push(`${at} ${d.asked}`);
      // A thread whose line still exists but no longer holds what was asked about.
      if (d.line && d.outdated) outdated.push(at);
      // The badge saying how many questions a line carries.
      const g = (n.children || []).find((c) => classesOf(c).includes("gut"));
      if (g && (g.dataset || {}).threads) gutter.push(g.dataset.threads);
    }
    if (inside && n.tagName === "TR") {
      const code = (n.children || []).find((c) => c.className === "code");
      // The whole class list. Reporting only the first left "del own" and "del"
      // indistinguishable, so whether a stage's own removal reads differently
      // from one that merely fell inside the window could not be checked at all.
      if (code) pane.push(`${cls || "row"} ${code.textContent}`);
    }
    (n.children || []).forEach((c) => walk(c, inside || classesOf(n).includes("stagepane")));
  };
  [registry.board, registry.fileGroups].forEach((root) => root && walk(root, false));

  console.log(JSON.stringify({
    asking,
    posted,
    side: registry.sideAnchor ? registry.sideAnchor.textContent : "",
    // Hidden is what closing does; the anchor text is left where it was.
    sideOpen: !!(registry.side && registry.side.hidden === false),
    // Which board holds the panel. Each tab hides the other's, so a panel in the wrong
    // one is open and visible to nobody.
    sideIn: !registry.side ? ""
      : registry.side.parentNode === registry.filesBoard ? "filesBoard"
      : registry.side.parentNode === registry.board ? "board" : "?",
    cards: cards.length,
    orphanCards: cards,
    pane,
    anchors,
    asked,
    outdated,
    gutter,
    // Composer rows still on the page. Sending is supposed to take it away.
    // The commit the rail has selected, by position.
    selectedCommit: (registry.commits ? registry.commits.children : [])
      .findIndex((b) => b["aria-current"] === "true"),
    // What each open composer holds, so a case can tell one kept from one rebuilt empty.
    composerTexts: [registry.board, registry.fileGroups]
      .filter(Boolean)
      .flatMap((r) => queryAll(r, "div.composer textarea"))
      .map((t) => t.value || ""),
    composers: [registry.board, registry.fileGroups]
      .filter(Boolean)
      .flatMap((r) => queryAll(r, "tr.composer-row")).length,
    orphans,
    anchored: threads.map((t) => t.id).filter((id) => !orphans.includes(id)),
    status: registry.qnaStatus ? registry.qnaStatus.textContent : "",
    rail: (registry.stageRail ? registry.stageRail.children : []).map(text),
    reviewed: (registry.progressText ? registry.progressText.textContent : "").split(" ")[0],
    // The files whose tick is from before they changed, which the header says out loud.
    stale: queryAll(registry.fileGroups, "div.file-bar")
      .filter((b) => queryAll(b, "span.changed").some((n) => !n.hidden))
      .map((b) => queryAll(b, "span.fpath")[0].textContent),
    squash: !!registry.squash && registry.squash.hidden === false,
    // The threads listed as asked on the commits view, by the text of each card.
    commitCards: (registry.commitThreadList ? registry.commitThreadList.children : []).map(text),
    tab: registry.board && registry.board.hidden === false ? "commits"
      : registry.filesView && registry.filesView.hidden === false ? "files" : "?",
    // What each reply box holds, so a case can tell a draft that survived a repaint from
    // one the repaint wiped.
    replies: replyBoxes().filter((b) => b.input.value).map((b) => `${b.thread}: ${b.input.value}`),
    // The question counts, as the page wrote them into data-q: where each is drawn, what
    // it says, and whether it is the quiet kind that only has resolved questions behind it.
    flags: [
      ["tab Files", registry.tabFiles],
      ["tab Commits", registry.tabCommits],
      ...(registry.stageRail ? registry.stageRail.children : []).map((b) => [
        "stage " + queryAll(b, "span.cb-head").map((h) => h.textContent).join(""), b]),
      ...queryAll(registry.fileGroups, "span.qflag").map((n) => ["file " + n.dataset.file, n]),
      ...queryAll(registry.fileGroups, "button.wholefile").map((n) => ["whole " + n.dataset.file, n]),
    ].filter(([, n]) => n && n.dataset && n.dataset.q)
      .map(([at, n]) => `${at}: ${n.dataset.q}${n.dataset.quiet === "true" ? " (quiet)" : ""}`),
  }));
  }, 10);
}, 50);
