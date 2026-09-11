// Run the built page's script against a minimal DOM and report what it drew.
//
//   node smoke.js <index.html>
//
// Exits non-zero when the script throws. A syntax check does not catch a const
// used above its declaration; running the script does, and that bug shipped a
// half-drawn page twice before this existed.
const fs = require("fs");

const mk = (tag) => {
  const node = {
    tagName: (tag || "div").toUpperCase(), children: [], dataset: {}, style: {},
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
globalThis.fetch = () => Promise.reject(new Error("no server while smoke testing"));
globalThis.setInterval = () => 0;

const html = fs.readFileSync(process.argv[2], "utf8");
const script = html.split("<script>")[1].split("</script>").slice(0, -1).join("</script>");

const count = (id) => (registry[id] ? registry[id].children.length : 0);

try {
  new Function(script)();
} catch (error) {
  console.error(`page script threw: ${error.constructor.name}: ${error.message}`);
  process.exit(1);
}

// Everything behind a click is otherwise never run, so a throw in it would ship. The
// files view and each stage in its rail are built only when their button is pressed.
const press = (node, what) => {
  if (!node || !node._on || !node._on.click) return false;
  try {
    node._on.click({ target: node, preventDefault() {} });
    return true;
  } catch (error) {
    console.error(`${what} threw: ${error.constructor.name}: ${error.message}`);
    process.exit(1);
  }
};

let stagesPressed = 0;
if (press(registry.tabFiles, "the files tab")) {
  const rail = registry.stageRail ? registry.stageRail.children : [];
  rail.forEach((btn, i) => { if (press(btn, `stage ${i} in the files rail`)) stagesPressed += 1; });
}

const drew = {
  commits: count("commits"),
  stages: count("stages"),
  notes: count("notesList"),
  figures: count("figures"),
  pane: count("pane"),
};
if (!drew.commits) {
  console.error("page script ran but drew no commits");
  process.exit(1);
}
console.log(
  `smoke ok: ${drew.commits} commits, ${drew.pane} pane sections, ` +
  `${drew.stages} stages, ${drew.notes} notes, ${drew.figures} figures` +
  (stagesPressed ? `, ${stagesPressed} files-rail views` : "")
);
