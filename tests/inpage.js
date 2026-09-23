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

const anchorOf = (n) => {
  const d = n.dataset || {};
  return `${d.view || "commits"} ${d.file}:${d.line} ${d.side}`;
};

/* Drive the page the way a reviewer does, one step at a time. Every step runs through
   the page's own handlers, so anything the page will not do fails here too.

   Steps: {open} expand every file box, {gutter} click a line's number, {type} fill the
   composer, {send} press the button, {stage} click a rail entry, {whole} press "Show the
   whole file", {closeSide} press the panel's X, {tick} run the poll. */
function drive(steps) {
  // getElementById hands out standalone nodes, so the page's subtrees hang off those
  // rather than off body. A search from body alone found nothing at all.
  const roots = () => [registry.fileGroups, registry.board, document.body].filter(Boolean);
  const all = (sel) => roots().flatMap((r) => queryAll(r, sel));
  const press = (n) => n && n._on && n._on.click && n._on.click();
  const done = [];
  for (const step of steps) {
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
setTimeout(() => {
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
  const asking = plan ? drive(plan.steps || []) : null;


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
    cards: cards.length,
    orphanCards: cards,
    pane,
    anchors,
    asked,
    outdated,
    gutter,
    // Composer rows still on the page. Sending is supposed to take it away.
    composers: [registry.board, registry.fileGroups]
      .filter(Boolean)
      .flatMap((r) => queryAll(r, "tr.composer-row")).length,
    orphans,
    anchored: threads.map((t) => t.id).filter((id) => !orphans.includes(id)),
    status: registry.qnaStatus ? registry.qnaStatus.textContent : "",
    rail: (registry.stageRail ? registry.stageRail.children : []).map(text),
    reviewed: (registry.progressText ? registry.progressText.textContent : "").split(" ")[0],
  }));
  }, 10);
}, 50);
