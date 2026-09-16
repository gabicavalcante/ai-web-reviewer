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

const mk = (tag) => {
  const node = {
    tagName: (tag || "div").toUpperCase(),
    children: [],
    dataset: {},
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
    focus() {}, closest() { return null; },
    setAttribute(k, v) { node[k] = v; }, getAttribute(k) { return node[k]; },
    matches() { return false; },
    // The page scans its own subtree for diff rows. Without these, paintThreads threw and
    // paintOrphans never ran, so every thread read as anchored whatever the page did.
    querySelectorAll() { return []; },
    querySelector() { return null; },
    scrollIntoView() {},
  };
  return node;
};

const registry = {};
globalThis.document = {
  title: "",
  body: mk("body"),
  createElement: mk,
  createTextNode: (t) => ({ nodeValue: t }),
  getElementById: (id) => (registry[id] = registry[id] || mk("div")),
  querySelectorAll: () => [],
  addEventListener: () => {},
  hidden: false,
};
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
globalThis.window = { confirm: () => false, location: { reload() {} } };
globalThis.setInterval = () => 0;

const threads = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
// The page reads its threads from /thread on the first poll, so that is where they go in.
globalThis.fetch = (url) =>
  String(url).startsWith("/thread")
    ? Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ threads, revision: "", watcher: true }),
      })
    : Promise.reject(new Error("only /thread is served here"));

const html = fs.readFileSync(process.argv[2], "utf8");
const script = html.split("<script>")[1].split("</script>").slice(0, -1).join("</script>");

try {
  new Function(script)();
} catch (error) {
  console.error(`page script threw: ${error.constructor.name}: ${error.message}`);
  process.exit(1);
}

// The poll is a promise; let it settle before reading what it drew.
setTimeout(() => {
  const text = (n) =>
    (n.children || []).length ? (n.children || []).map(text).join(" ") : (n.textContent || "");
  // An orphan card is identified by the question it carries, not by the thread id: the
  // card never prints the id, so looking for it found nothing and every thread read as
  // anchored whatever the page had actually done with it.
  const cards = (registry.orphanList ? registry.orphanList.children : []).map(text);
  const orphans = threads
    .filter((t) => cards.some((card) => card.includes(t.question)))
    .map((t) => t.id);
  console.log(JSON.stringify({
    cards: cards.length,
    orphans,
    anchored: threads.map((t) => t.id).filter((id) => !orphans.includes(id)),
  }));
}, 50);
