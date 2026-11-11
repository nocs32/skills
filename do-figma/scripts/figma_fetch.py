#!/usr/bin/env python3
"""Read Figma frames through the REST API, cached to disk.

The Dev Mode MCP is metered by Figma (200/day, 10/min on a Pro Dev seat) and one audit wave
exhausts it. REST is a separate, far more generous quota, and it states five things the MCP does
not: rotation baked into absoluteBoundingBox, minHeight beside height, absoluteRenderBounds beside
the geometric box, `visible: false`, and instance `overrides`.

REST cannot serve variable NAMES. Those are bought once each from the MCP's get_variable_defs and
kept in ~/.claude/figma/<fileKey>/variables.json -- keyed by Figma file, so every worktree, clone
and project sharing that design file reuses one dictionary. See --vars / --vars-merge.

Usage (NODE is a full Figma URL, or a bare node id once a URL has been used here):
    figma_fetch.py --read NODE             # ONE call: variable status + tree + every value
    figma_fetch.py NODE                    # geometry tree only (fills, padding, gap, font per line)
    figma_fetch.py --tokens NODE           # bound props -> figma name, value, local token
    figma_fetch.py --vars NODE             # dictionary coverage; run BEFORE any MCP call
    figma_fetch.py --vars-merge NODE FILE  # fold a get_variable_defs payload in (FILE or - for stdin)
    figma_fetch.py --diff NODE FILE        # compare measure.js output with the frame (FILE or -);
                                           #   prints only what differs, --all prints every row
    figma_fetch.py --image NODE [scale]    # render a PNG (default 2x), once per node
    figma_fetch.py --doctor                # check token, project record and token scale
    figma_fetch.py --set-tokens DIR [--prefix P]   # record this project's design-token source

Output size: the harness parks tool output past ~30k characters in a file and shows 2 KB of it, so
--read is sized to land inline whole (READ_BUDGET). The values section is compact; the tree gets
the rest and is cut by depth to fit, each collapsed subtree ending in (+N nodes) — expand one with
`--read <its id>`. `--depth N` sets the cut and `--full` removes it: both are for a human at a
terminal, since in a session what they print does not arrive. Hidden subtrees collapse unless
asked for directly.

Token: $FIGMA_ALL_ACCESS, $FIGMA_ACCESS_TOKEN or $FIGMA_TOKEN. Never printed.
Nothing is written into the project except the frame cache. Per-project settings (the design-token
source, the last file key) live in ~/.claude/figma/projects/<project>.json, keyed by git remote so
worktrees and clones share one record. Frame cache: <project root>/.figma-cache/<fileKey>/.
"""

import collections
import contextlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request

HOME_STORE = pathlib.Path.home() / ".claude" / "figma"
TOKEN_VARS = ("FIGMA_ALL_ACCESS", "FIGMA_ACCESS_TOKEN", "FIGMA_TOKEN")

_FILE_KEY = None


def _git(*args) -> str:
    try:
        out = subprocess.run(("git", *args), capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def project_key() -> str:
    """Stable id for 'this project'. The remote url first, so every worktree and clone of a
    repo shares one record; then the main repo's git dir, which worktrees also agree on."""
    raw = _git("remote", "get-url", "origin")
    if not raw:
        # --git-common-dir can be relative ('.git'); from a worktree it points at the main repo
        gitdir = _git("rev-parse", "--git-common-dir")
        raw = str((pathlib.Path.cwd() / gitdir).resolve()) if gitdir else ""
    raw = raw or str(pathlib.Path.cwd().resolve())
    raw = re.sub(r"^(https?://|git@)|\.git/?$|/\.git$", "", raw).replace(":", "/")
    return re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-")[:120]


def project_root() -> pathlib.Path:
    top = _git("rev-parse", "--show-toplevel")
    return pathlib.Path(top) if top else pathlib.Path.cwd().resolve()


def record_path() -> pathlib.Path:
    d = HOME_STORE / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{project_key()}.json"


def record() -> dict:
    p = record_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def write_record(**kv) -> dict:
    r = record()
    r.update({k: v for k, v in kv.items() if v is not None})
    record_path().write_text(json.dumps(r, indent=1))
    return r


def parse_node(arg: str) -> str:
    """Accept a Figma URL, or a bare node id. A URL also supplies the file key, which is
    remembered for this project so later calls can use bare ids."""
    global _FILE_KEY
    if arg.startswith("http"):
        u = urllib.parse.urlparse(arg)
        parts = [p for p in u.path.split("/") if p]
        for i, p in enumerate(parts):
            if p in ("design", "file") and i + 1 < len(parts):
                _FILE_KEY = parts[i + 1]
        node = urllib.parse.parse_qs(u.query).get("node-id", [""])[0]
        if not node:
            sys.exit(f"no node-id in {arg}")
        if _FILE_KEY:
            write_record(lastFileKey=_FILE_KEY)
        return node.replace("-", ":")
    return arg.replace("-", ":")


def file_key() -> str:
    key = _FILE_KEY or os.environ.get("FIGMA_FILE_KEY") or record().get("lastFileKey")
    if not key:
        sys.exit(
            "No Figma file key.\n"
            "  Pass the full Figma URL — figma.com/design/<fileKey>/Name?node-id=1-2 — and it is\n"
            "  remembered for this project, so bare node ids work from then on."
        )
    return key


def cache_dir() -> pathlib.Path:
    d = project_root() / ".figma-cache" / file_key()
    d.mkdir(parents=True, exist_ok=True)
    return d


def dict_path() -> pathlib.Path:
    d = HOME_STORE / file_key()
    d.mkdir(parents=True, exist_ok=True)
    return d / "variables.json"


def tokens_spec() -> dict:
    return record().get("tokens") or {}


def tokens_declared_none() -> bool:
    return bool(tokens_spec().get("none"))


def tokens_dir():
    """None when never configured. Configured-but-missing is fatal: silently dropping the
    token scale is how literals get written into code that should carry tokens."""
    spec = tokens_spec()
    if not spec.get("dir"):
        return None
    d = pathlib.Path(spec["dir"])
    if not d.is_absolute():
        d = (project_root() / d).resolve()
    if not d.is_dir():
        sys.exit(
            f"The token scale recorded for this project points at {d}, which does not exist.\n"
            f"  Re-run:  figma_fetch.py --set-tokens <dir> [--prefix <p>]\n"
            f"  Or clear it:  figma_fetch.py --set-tokens none\n"
            f"  (record: {record_path()})\n"
            "  Refusing to run without it: an unmapped value silently becomes a literal."
        )
    return d


def tokens_prefix() -> str:
    return tokens_spec().get("prefix", "")


def set_tokens(dir_arg: str, prefix: str) -> None:
    if dir_arg.lower() in ("none", "clear", ""):
        # Recorded, not merely absent: plenty of projects write px and hex directly in
        # styled-components or CSS. Saying so stops every later session re-hunting for a
        # theme file that does not exist.
        write_record(tokens={"none": True})
        print(f"recorded: this project has no token scale — values are written raw")
        print(f"  ({record_path()})")
        return
    d = pathlib.Path(dir_arg)
    if not d.is_absolute():
        d = (pathlib.Path.cwd() / d).resolve()
    if not d.is_dir():
        sys.exit(f"{d} is not a directory")
    try:
        rel = str(d.relative_to(project_root()))
    except ValueError:
        rel = str(d)
    write_record(tokens={"dir": rel, "prefix": prefix})
    lookup = repo_tokens()
    print(f"token scale -> {rel}  ({len(lookup)} distinct values), prefix {prefix!r}")
    kinds = {}
    for v in lookup:
        kinds[value_kind(v)] = kinds.get(value_kind(v), 0) + 1
    if kinds:
        print("  by kind:  " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())))
    missing = sorted({
        PROP_CATEGORY[p] for p in PROP_CATEGORY if not scale_covers(p, lookup)
    })
    if missing:
        print(f"  not tokenised: {', '.join(missing)} — those values are written raw")
    print(f"recorded in {record_path()}")
    if not lookup:
        sys.exit(
            "WARNING: resolved no tokens. Supported: a directory or single file of TS/JS object\n"
            "  literals, CSS custom properties, SCSS/Less variables, or JSON (incl. DTCG $value)."
        )


def _token() -> str:
    for var in TOKEN_VARS:
        if os.environ.get(var):
            return os.environ[var]
    sys.exit(
        "No Figma token in the environment.\n"
        f"  Set one of: {', '.join(TOKEN_VARS)}\n"
        "  Create a personal access token at figma.com -> Settings -> Security ->\n"
        "  Personal access tokens, then export it from your shell profile."
    )


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"X-Figma-Token": _token()})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sys.exit(
                f"Figma returned 404 for file key {file_key()!r}.\n"
                "  The key is the segment after /design/ in the Figma URL."
            )
        if e.code == 403:
            sys.exit(
                f"Figma returned 403 for file key {file_key()!r}.\n"
                "  The token is expired, or lacks access to this file."
            )
        sys.exit(f"Figma returned {e.code}: {e.reason}")


def doctor() -> None:
    ok = True
    have = next((v for v in TOKEN_VARS if os.environ.get(v)), None)
    print(f"token          {'set via $' + have if have else 'MISSING — see --help'}")
    ok &= bool(have)
    print(f"project        {project_key()}")
    print(f"project root   {project_root()}")
    print(f"record         {record_path()}{'' if record_path().exists() else '  (none yet)'}")
    last = record().get("lastFileKey")
    print(f"file key       {last or '(none — pass a Figma URL once)'}")
    spec = tokens_spec()
    if tokens_declared_none():
        print("token scale    none — recorded: this project writes raw values")
    elif not spec.get("dir"):
        print("token scale    NOT CHECKED — look for one, then record the answer:")
        print("               figma_fetch.py --set-tokens <dir> [--prefix <p>]")
        print("               figma_fetch.py --set-tokens none      (if there is no scale)")
    else:
        d = tokens_dir()
        n = len(repo_tokens()) if d else 0
        print(f"token scale    {d}  ({n} distinct values), prefix {tokens_prefix()!r}")
        if not n:
            print("               WARNING: resolved no tokens; check the directory and format")
            ok = False
    if have:
        me = _get("https://api.figma.com/v1/me")
        print(f"figma user     {me.get('email', '?')}")
    sys.exit(0 if ok else 1)


def fetch(node_id: str) -> dict:
    return _get(f"https://api.figma.com/v1/files/{file_key()}/nodes?ids={node_id}")


def load(node_id: str) -> dict:
    path = cache_dir() / f"{node_id.replace(':', '-')}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = fetch(node_id)
    if not data.get("nodes"):
        sys.exit(f"Figma returned no node {node_id!r} in file {file_key()!r}.")
    path.write_text(json.dumps(data, indent=1))
    return data


def styles_map(node_id: str) -> dict:
    """styleId -> style name, e.g. {"1:23": "Typography/Body2"}."""
    data = load(node_id)
    key = node_id if node_id in data["nodes"] else list(data["nodes"])[0]
    return {k: v["name"] for k, v in data["nodes"][key].get("styles", {}).items()}


def document(node_id: str) -> dict:
    data = load(node_id)
    key = node_id if node_id in data["nodes"] else list(data["nodes"])[0]
    return data["nodes"][key]["document"]


# --- geometry table ---------------------------------------------------------


# The harness parks tool output past ~30k characters in a file and shows a 2 KB preview. A read
# that size never reaches the agent; the round that follows is spent paging it back with head and
# sed, one turn each, and every turn re-reads the whole conversation. So --read is sized in bytes
# to land inline, whole: the values section is compact, and the tree takes what is left, cut by
# depth, with every cut subtree saying how to expand it.
READ_BUDGET = 24_000


def _count(n: dict) -> int:
    return 1 + sum(_count(c) for c in n.get("children", []))


def _hidden(n: dict) -> bool:
    # Invisible has two forms and only one of them is `visible`. An opacity-0 node still
    # reports full geometry, so measuring one is a silent, total waste of a round.
    return n.get("visible") is False or not n.get("opacity", 1)


def _capture(fn, *args) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def _fit_depth(entries: list, budget: int) -> int:
    """Deepest limit at which every entry down to it, plus a (+N nodes) tail on each node cut
    there, fits the byte budget. Never less than 1: the root's own children are always shown."""
    max_d = max(e[0] for e in entries)
    best = 1
    for limit in range(1, max_d + 1):
        size = 0
        for d, line, kids, desc, hidden in entries:
            if d > limit:
                continue
            size += len(line) + 1
            if kids and (hidden or d == limit):
                size += len(f"  (+{desc} hidden nodes)")
        if size > budget:
            break
        best = limit
    return best


def _props(n: dict) -> str:
    """The values a builder needs from this node, on its own line — so the tree answers what
    used to take a python one-liner against the raw JSON per node."""
    out = []
    lm = n.get("layoutMode")
    if lm:
        out.append({"HORIZONTAL": "H", "VERTICAL": "V"}.get(lm, lm))
        if n.get("layoutWrap") == "WRAP":
            out.append("wrap")
        # justify / align on the main and cross axis; MIN is the default and is not shown
        j = {"CENTER": "center", "MAX": "end", "SPACE_BETWEEN": "space-between"}.get(
            n.get("primaryAxisAlignItems"))
        a = {"CENTER": "center", "MAX": "end", "BASELINE": "baseline"}.get(
            n.get("counterAxisAlignItems"))
        if j:
            out.append(f"justify={j}")
        if a:
            out.append(f"align={a}")
    # how the node sizes itself inside its parent: fill / hug; FIXED is the default and not shown
    for axis, key, legacy in (("w", "layoutSizingHorizontal", "primaryAxisSizingMode"),
                              ("h", "layoutSizingVertical", "counterAxisSizingMode")):
        mode = n.get(key)
        if mode == "FILL":
            out.append(f"{axis}=fill")
        elif mode == "HUG":
            out.append(f"{axis}=hug")
    if n.get("layoutAlign") == "STRETCH" and not n.get("layoutSizingHorizontal") \
            and not n.get("layoutSizingVertical"):
        out.append("stretch")
    if n.get("layoutGrow"):
        out.append("grow")
    if n.get("clipsContent"):
        out.append("clip")
    c = n.get("constraints") or {}
    pin = [v.lower() for v in (c.get("horizontal"), c.get("vertical"))
           if v and v not in ("LEFT", "TOP")]
    if pin:
        out.append("pin=" + ",".join(pin))
    op = n.get("opacity")
    if op is not None and 0 < op < 1:
        out.append(f"opacity={op:g}")
    pads = [n.get(k) or 0 for k in ("paddingTop", "paddingRight", "paddingBottom", "paddingLeft")]
    if any(pads):
        t, r, b, l = (f"{p:g}" for p in pads)
        if len(set(pads)) == 1:
            out.append(f"pad={t}")
        elif t == b and r == l:
            out.append(f"pad={t},{r}")
        else:
            out.append(f"pad={t},{r},{b},{l}")
    if n.get("itemSpacing"):
        out.append(f"gap={n['itemSpacing']:g}")
    if n.get("counterAxisSpacing"):
        out.append(f"rowgap={n['counterAxisSpacing']:g}")
    radii = n.get("rectangleCornerRadii")
    if radii and len(set(radii)) > 1:
        out.append("r=" + ",".join(f"{x:g}" for x in radii))
    elif isinstance(n.get("cornerRadius"), (int, float)) and n["cornerRadius"]:
        out.append(f"r={n['cornerRadius']:g}")
    fill = _value_of(n, "fills") if _present(n, "fills") else None
    if fill:
        out.append(("color=" if n.get("type") == "TEXT" else "fill=") + fill)
    stroke = _value_of(n, "strokes") if _present(n, "strokes") else None
    if stroke:
        s = f"stroke={stroke}/{n.get('strokeWeight', 1):g}"
        if n.get("strokeAlign") in ("OUTSIDE", "CENTER"):
            s += "/" + n["strokeAlign"].lower()   # INSIDE is Figma's default; CSS is outside
        sides = n.get("individualStrokeWeights")
        if sides:
            s += "/" + ",".join(f"{sides.get(k, 0):g}" for k in ("top", "right", "bottom", "left"))
        out.append(s)
    st = n.get("style") or {}
    if st.get("fontSize"):
        font = f"font={st['fontSize']:g}/{int(st.get('fontWeight', 400))}"
        if st.get("lineHeightPx"):
            font += f"/{st['lineHeightPx']:g}"
        if st.get("letterSpacing"):
            font += f"/ls{st['letterSpacing']:g}"
        if st.get("fontFamily"):
            font += f" {st['fontFamily']}"
        out.append(font)
        ta = st.get("textAlignHorizontal")
        if ta and ta != "LEFT":
            out.append(f"text-align={ta.lower()}")
        if st.get("textCase") and st["textCase"] != "ORIGINAL":
            out.append(f"case={st['textCase'].lower()}")
        if st.get("textDecoration") and st["textDecoration"] != "NONE":
            out.append(st["textDecoration"].lower())
    if n.get("type") == "TEXT":
        ar = n.get("textAutoResize")
        if ar == "TRUNCATE" or n.get("textTruncation") == "ENDING":
            out.append("truncate")
        elif ar == "NONE" and n.get("absoluteBoundingBox"):
            out.append("fixed-box")
        if n.get("maxLines"):
            out.append(f"max-lines={n['maxLines']}")
        if any(t != "NONE" for t in n.get("lineTypes", [])):
            out.append("list")
        if n.get("characterStyleOverrides"):
            out.append("mixed-styles")
        if n.get("characters"):
            s = n["characters"].replace("\n", "⏎")
            out.append(f'text="{s[:60]}{"…" if len(s) > 60 else ""}"')
    for e in n.get("effects", []):
        if not e.get("visible", True):
            continue
        t = e.get("type", "")
        if t in ("DROP_SHADOW", "INNER_SHADOW"):
            col = e.get("color") or {}
            o = e.get("offset") or {}
            a = round(col.get("a", 1) * 255)
            out.append(f"{'inner-' if t == 'INNER_SHADOW' else ''}shadow="
                       f"{o.get('x', 0):g},{o.get('y', 0):g},{e.get('radius', 0):g},"
                       f"{e.get('spread', 0):g},{_hex(col)}{a:02x}")
        elif t == "LAYER_BLUR":
            out.append(f"blur={e.get('radius', 0):g}")
        elif t == "BACKGROUND_BLUR":
            out.append(f"backdrop-blur={e.get('radius', 0):g}")
    if n.get("type") in ("INSTANCE",) and n.get("componentProperties"):
        props = [f"{k.split('#')[0]}={v.get('value')}" for k, v in n["componentProperties"].items()
                 if v.get("type") in ("VARIANT", "BOOLEAN") and v.get("value") is not None]
        if props:
            out.append("variant[" + " ".join(props)[:80] + "]")
    return " ".join(out)


def _tree_entries(doc: dict, full: bool) -> list:
    """Every line the tree could print, as (depth, line, has_kids, descendants, collapsed_hidden).
    Hidden subtrees are left out unless `full`, except the node asked for itself — otherwise
    `--read <hidden id>` could never show what is inside a state."""
    out = []

    def walk(n, d, parent_bb):
        bb = n.get("absoluteBoundingBox")
        rb = n.get("absoluteRenderBounds")
        if bb:
            rx = round(bb["x"] - parent_bb["x"], 2)
            ry = round(bb["y"] - parent_bb["y"], 2)
            geom = f"{rx:g},{ry:g} {round(bb['width'], 2):g}x{round(bb['height'], 2):g}"
        else:
            geom = "-"
        extra = []
        if n.get("minHeight") is not None:
            extra.append(f"minH={n['minHeight']:g}")
        if abs(n.get("rotation") or 0) > 1e-4:
            extra.append(f"rot={round(n['rotation'], 4)}")
        if rb and bb and abs(rb["width"] - bb["width"]) > 0.01:
            extra.append(f"render_w={round(rb['width'], 2):g}")
        hidden = _hidden(n)
        if n.get("visible") is False:
            extra.append("HIDDEN(visible=false)")
        elif hidden:
            extra.append("HIDDEN(opacity=0)")
        bound = sorted(n.get("boundVariables", {}))
        if bound:
            extra.append(f"bound={','.join(bound)}")
        kids = n.get("children", [])
        line = "  " * d + "  ".join(x for x in (f"{n['id']}", repr(n.get("name", "")),
                                                f"[{geom}]", _props(n), " ".join(extra)) if x)
        collapsed = hidden and not full and d > 0
        out.append((d, line, bool(kids), _count(n) - 1, collapsed))
        if not collapsed:
            for c in kids:
                walk(c, d + 1, bb or parent_bb)

    walk(doc, 0, doc["absoluteBoundingBox"])
    return out


def table_text(node_id: str, depth=None, full: bool = False, budget: int = READ_BUDGET) -> str:
    doc = document(node_id)
    root = doc["absoluteBoundingBox"]
    entries = _tree_entries(doc, full)
    head = (f"# {doc.get('name')} — {root['width']:g}x{root['height']:g}  "
            f"({_count(doc)} nodes; offsets relative to parent)\n")
    if full:
        limit = None
    elif depth is not None:
        limit = depth
    else:
        limit = _fit_depth(entries, budget - len(head) - 160)
    lines = [head.rstrip("\n")]
    if limit is not None and any(d > limit for d, *_ in entries):
        lines.append(f"# cut at depth {limit} to arrive whole. A line ending in (+N nodes) is a "
                     f"collapsed subtree: figma_fetch.py --read <that id> opens it. Do not pipe "
                     f"this through head or sed.")
    for d, line, kids, desc, collapsed in entries:
        if limit is not None and d > limit:
            continue
        tail = ""
        if kids and collapsed:
            tail = f"  (+{desc} hidden nodes)"
        elif kids and limit is not None and d == limit:
            tail = f"  (+{desc} nodes)"
        lines.append(line + tail)
    return "\n".join(lines) + "\n"


def table(node_id: str, depth=None, full: bool = False) -> None:
    sys.stdout.write(table_text(node_id, depth, full))


GENERIC_NAME = re.compile(r"^(Frame|Vector|Rectangle|Ellipse|Group|Line|Union|Subtract)\s*\d*$", re.I)


def search_terms(doc: dict, limit: int = 12) -> None:
    """One rg command that finds the component if it exists: the strings the frame renders and the
    components it instantiates. Three separate searches — by name, by string, by prop — were three
    turns; this is one."""
    strings, names = [], []

    def usable(s: str) -> bool:
        """Specific enough to identify a component: UI copy, not data. Single short words
        ('Name', 'plus') match half the codebase; emails, dates and counts match fixtures."""
        if not (6 <= len(s) <= 40) or "@" in s:
            return False
        if sum(ch.isdigit() for ch in s) > len(s) / 4:
            return False
        return len(s.split()) >= 2 or len(s) >= 10

    def walk(n):
        if _hidden(n):
            return
        if n.get("type") == "TEXT":
            s = " ".join((n.get("characters") or "").split())
            if usable(s) and s not in strings:
                strings.append(s)
        elif n.get("type") in ("INSTANCE", "COMPONENT", "COMPONENT_SET"):
            name = (n.get("name") or "").split("/")[-1].strip()
            if usable(name) and not GENERIC_NAME.match(name) and name not in names:
                names.append(name)
        for c in n.get("children", []):
            walk(c)

    walk(doc)
    root = (doc.get("name") or "").strip()
    terms = ([root] if usable(root) and not GENERIC_NAME.match(root) else []) \
        + strings[:limit // 2] + names
    terms = list(dict.fromkeys(t for t in terms if t))[:limit]
    print("## does it already exist? — ONE search, then read only the top hits")
    if not terms:
        print("## (nothing in the frame is specific enough to search for; search by the props "
              "the component would take)")
        return
    quoted = " ".join("-e '" + t.replace("'", "'\\''") + "'" for t in terms)
    print("rg -n -i -w --type-add 'ui:*.{ts,tsx,js,jsx,mjs,vue,svelte,css,scss,less}' -tui "
          f"--glob '!node_modules' --glob '!.figma-cache' {quoted} .")
    print("## add the prop names you would expect, run it once; a near-miss needing a variant is the "
          "common case")


def read(node_id: str, depth=None, full: bool = False) -> None:
    """Everything the builder needs from one frame, in one call: variable status, the tree, every
    concrete value, and the one search that settles existing-or-new. One fetch, one output, no
    follow-up reads."""
    status = _capture(vars_status, node_id)
    values = tokens_text(node_id)
    search = _capture(search_terms, document(node_id))
    fixed = len(status) + len(values) + len(search) + 3
    tree = table_text(node_id, depth, full, budget=max(READ_BUDGET - fixed, 6_000))
    sys.stdout.write(status + "\n" + tree + "\n" + values + "\n" + search)


# --- repo token map ---------------------------------------------------------


TOKEN_SUFFIXES = (".ts", ".tsx", ".js", ".mjs", ".cjs", ".mts",
                  ".css", ".scss", ".sass", ".less", ".json")


def _parse_js(text: str, stem: str) -> dict:
    """Object literals: nested `group: {}` blocks with `name: "value"` leaves."""
    out, stack = {}, [stem]
    for line in text.splitlines():
        line = line.strip()
        opened = re.match(r"""^["']?([\w-]+)["']?\s*:\s*\{$""", line)
        leaf = re.match(r"""^["']?([\w-]+)["']?\s*:\s*["']([^"']*)["']""", line)
        if opened:
            stack.append(opened.group(1))
        elif leaf:
            out.setdefault(leaf.group(2), []).append(".".join(stack + [leaf.group(1)]))
        elif line.startswith("}") and len(stack) > 1:
            stack.pop()
    return out


def _parse_css(text: str) -> dict:
    """CSS custom properties, SCSS `$vars` and Less `@vars`. The name is what code writes."""
    out = {}
    for m in re.finditer(r"(--[\w-]+|\$[\w-]+|@[\w-]+)\s*:\s*([^;{}\n]+)", text):
        value = m.group(2).strip().strip('"\'')
        if value and not value.startswith(("var(", "$", "@")):
            out.setdefault(value, []).append(m.group(1))
    return out


def _parse_json(data, path, out) -> None:
    """Plain nested JSON, and the DTCG format where a leaf is {"$value": ...}."""
    if isinstance(data, dict):
        if "$value" in data and not isinstance(data["$value"], (dict, list)):
            out.setdefault(str(data["$value"]), []).append(".".join(path))
            return
        for k, v in data.items():
            if not k.startswith("$"):
                _parse_json(v, path + [k], out)
    elif isinstance(data, (str, int, float)):
        out.setdefault(str(data), []).append(".".join(path))


def repo_tokens() -> dict:
    """value -> [token names]. Accepts a directory or a single file, in any of the common
    shapes: TS/JS object literals, CSS custom properties, SCSS/Less variables, or JSON
    (including the DTCG `$value` format). A project may have none of this, or cover only
    some categories — both are normal, and neither lowers the bar on reproducing values."""
    out: dict = {}
    root = tokens_dir()
    if root is None:
        return out
    files = [root] if root.is_file() else [
        f for f in sorted(root.rglob("*"))
        if f.is_file() and f.suffix in TOKEN_SUFFIXES and f.name != "index.ts"
    ]
    for f in files:
        try:
            text = f.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if f.suffix == ".json":
            try:
                _parse_json(json.loads(text), [f.stem], out)
            except json.JSONDecodeError:
                continue
        elif f.suffix in (".css", ".scss", ".sass", ".less"):
            for v, names in _parse_css(text).items():
                out.setdefault(v, []).extend(names)
        else:
            for v, names in _parse_js(text, f.stem).items():
                out.setdefault(v, []).extend(names)
    return {v: sorted(set(n)) for v, n in out.items()}


def value_kind(value: str) -> str:
    """What sort of thing a value is. Filtering on this is format-agnostic — it works
    whether the scale is `theme.spacing.s16`, `--padding-main`, or `$space-4`."""
    v = str(value).strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3,8}|(rgba?|hsla?)\(.*\)", v) or v in ("transparent", "currentcolor"):
        return "color"
    if re.fullmatch(r"-?[\d.]+(px|rem|em|%)?", v):
        return "length" if re.search(r"px|rem|em|%", v) or v in ("0",) else "number"
    return "text"


# Words that place a token name in a category. Checked against the whole name, so it works
# for `theme.spacing.s16`, `--padding-main` and `space-4` alike.
CATEGORY_WORDS = {
    "spacing": ("spac", "space", "gap", "pad", "inset", "margin", "size"),
    "radius": ("radius", "round", "corner"),
    "borderWidth": ("border-width", "borderwidth", "stroke", "width"),
    "fontSize": ("font-size", "fontsize", "text-size", "textsize"),
    "lineHeight": ("line-height", "lineheight", "leading"),
    "fontWeight": ("weight",),
    "fontFamily": ("family", "font-family", "fontfamily"),
    "color": ("color", "colour", "palette"),
}
PROP_CATEGORY = {
    "paddingLeft": "spacing", "paddingRight": "spacing", "paddingTop": "spacing",
    "paddingBottom": "spacing", "itemSpacing": "spacing", "counterAxisSpacing": "spacing",
    "size": "spacing", "width": "spacing", "height": "spacing",
    "rectangleCornerRadii": "radius", "cornerRadius": "radius",
    "topLeftRadius": "radius", "topRightRadius": "radius",
    "bottomLeftRadius": "radius", "bottomRightRadius": "radius",
    "strokeWeight": "borderWidth",
    "fontSize": "fontSize", "lineHeight": "lineHeight",
    "fontWeight": "fontWeight", "fontFamily": "fontFamily",
    "fills": "color", "strokes": "color",
}
PROP_KIND = {
    "fills": "color", "strokes": "color",
    "fontFamily": "text", "fontWeight": "number",
}


# Which token scale a Figma property must resolve against. Without this a 16px padding
# also "matches" border.radius.r16 and font.size.s16, and the builder picks by eye.
SCALE_OF = {
    "fills": "color", "strokes": "color",
    "paddingLeft": "spacing", "paddingRight": "spacing", "paddingTop": "spacing",
    "paddingBottom": "spacing", "itemSpacing": "spacing", "counterAxisSpacing": "spacing",
    "size": "spacing", "width": "spacing", "height": "spacing",
    "rectangleCornerRadii": "border.radius", "cornerRadius": "border.radius",
    "topLeftRadius": "border.radius", "topRightRadius": "border.radius",
    "bottomLeftRadius": "border.radius", "bottomRightRadius": "border.radius",
    "strokeWeight": "border.width",
    "fontSize": "font.size", "lineHeight": "font.lineHeight",
    "fontWeight": "font.weight", "fontFamily": "font.family",
    "opacity": "opacity", "effects": "shadow",
}


def _hex(color: dict) -> str:
    r, g, b = (round(color[c] * 255) for c in ("r", "g", "b"))
    return f"#{r:02x}{g:02x}{b:02x}"


def _value_of(node: dict, prop: str):
    """The resolved value of a variable-bound property, as the repo would write it."""
    if prop == "fills":
        fills = [f for f in node.get("fills", []) if f.get("type") == "SOLID"]
        return _hex(fills[0]["color"]) if fills else None
    if prop == "strokes":
        strokes = [s for s in node.get("strokes", []) if s.get("type") == "SOLID"]
        return _hex(strokes[0]["color"]) if strokes else None
    # Typography lives under `style`, not on the node itself.
    style = node.get("style", {})
    if prop in ("fontSize", "lineHeight", "fontWeight", "fontFamily"):
        v = style.get("lineHeightPx" if prop == "lineHeight" else prop)
        if prop == "fontFamily":
            return v
        if prop == "fontWeight":
            return str(int(v)) if v is not None else None
        return f"{round(v, 2):g}px" if v is not None else None
    # `size` is a {x, y} pair; report whichever axis is actually bound.
    if prop == "size":
        bb = node.get("absoluteBoundingBox") or {}
        axes = node.get("boundVariables", {}).get("size", {})
        parts = [
            f"{round(bb[k], 2):g}px"
            for a, k in (("x", "width"), ("y", "height"))
            if a in axes and bb.get(k) is not None
        ]
        if len(parts) == 1:
            return parts[0]
        return parts[0] if len(parts) == 2 and parts[0] == parts[1] else None
    if prop == "rectangleCornerRadii":
        # Figma binds under `rectangleCornerRadii` but stores the value in `cornerRadius`
        # when all four corners are equal, and only fills the array when they differ.
        radii = node.get("rectangleCornerRadii")
        if not radii:
            r = node.get("cornerRadius")
            return f"{round(r, 2):g}px" if isinstance(r, (int, float)) else "0px"
        # per-corner, e.g. [6, 0, 0, 6] for a left-rounded segment. One distinct non-zero
        # radius is the normal case; the geometry table shows which corners carry it.
        uniq = {round(r, 2) for r in radii if r}
        return f"{uniq.pop():g}px" if len(uniq) == 1 else None
    v = node.get(prop)
    if isinstance(v, (int, float)):
        return f"{round(v, 2):g}px"
    # Figma omits a spacing property whose value is 0, but still records the binding.
    if prop in ("paddingLeft", "paddingRight", "paddingTop", "paddingBottom",
                "itemSpacing", "counterAxisSpacing", "strokeWeight"):
        return "0px"
    return None


# Properties worth reporting when they are NOT bound to a variable. Plenty of designs --
# and plenty of design systems -- use raw px and hex throughout; those values still have to be
# reproduced exactly, so they cannot be invisible just because no variable points at them.
RAW_PROPS = (
    "fills", "strokes", "strokeWeight", "cornerRadius", "rectangleCornerRadii",
    "itemSpacing", "counterAxisSpacing",
    "paddingLeft", "paddingRight", "paddingTop", "paddingBottom",
    "fontFamily", "fontSize", "fontWeight", "lineHeight",
)


def _present(node: dict, prop: str) -> bool:
    """True only when the node actually carries the property. Distinct from _value_of, which
    defaults an absent-but-bound spacing property to 0px."""
    if prop in ("fills", "strokes"):
        return any(x.get("type") == "SOLID" for x in node.get(prop, []))
    if prop in ("fontFamily", "fontSize", "fontWeight", "lineHeight"):
        key = "lineHeightPx" if prop == "lineHeight" else prop
        return node.get("style", {}).get(key) is not None
    if prop == "rectangleCornerRadii":
        return bool(node.get("rectangleCornerRadii")) or isinstance(
            node.get("cornerRadius"), (int, float)
        )
    if prop == "cornerRadius":
        return isinstance(node.get("cornerRadius"), (int, float)) and not node.get(
            "rectangleCornerRadii"
        )
    return isinstance(node.get(prop), (int, float))


def _match_tokens(prop: str, value, lookup: dict) -> list:
    if prop == "fontFamily":
        # a scale stores a full stack ("Geist, sans-serif"); Figma names only the face
        cands = [n for v, ns in lookup.items() if str(v).startswith(str(value)) for n in ns]
    else:
        cands = list(lookup.get(value, []))
    words = CATEGORY_WORDS.get(PROP_CATEGORY.get(prop, ""), ())
    if words:
        narrowed = [c for c in cands if any(w in c.lower() for w in words)]
        # An unhinted scale (flat names like `s16`) keeps every same-value candidate rather
        # than reporting nothing.
        cands = narrowed or cands
    return sorted(set(cands))


def scale_covers(prop: str, lookup: dict) -> bool:
    """Whether the scale holds anything of the right sort for this property. A project that
    tokenises colour but not spacing should not have every padding flagged as a gap."""
    want = PROP_KIND.get(prop, "length")
    return any(value_kind(v) == want for v in lookup)


def figma_name(node: dict, prop: str, known: dict) -> str:
    ref = node.get("boundVariables", {}).get(prop)
    ids = []
    if isinstance(ref, dict) and "id" in ref:
        ids = [ref["id"]]
    elif isinstance(ref, dict):
        ids = [a["id"] for a in ref.values() if isinstance(a, dict) and "id" in a]
    elif isinstance(ref, list):
        ids = [a["id"] for a in ref if isinstance(a, dict) and "id" in a]
    return next((known[i] for i in ids if i in known), "?")


def tokens(node_id: str) -> None:
    sys.stdout.write(tokens_text(node_id))


def tokens_text(node_id: str) -> str:
    """Every concrete value in the frame, grouped by property so the section stays a few KB
    however large the frame — it has to share the inline budget with the tree."""
    doc = document(node_id)
    lookup = repo_tokens()
    known = read_dict()
    prefix = f"{tokens_prefix()}." if tokens_prefix() else ""
    bound, raw = [], []

    def walk(n, hidden=False):
        hidden = hidden or n.get("visible") is False or not n.get("opacity", 1)
        if hidden:
            for c in n.get("children", []):
                walk(c, True)
            return
        b = n.get("boundVariables", {})
        for prop in sorted(b):
            value = _value_of(n, prop)
            if value is not None:
                bound.append((figma_name(n, prop, known), prop, value,
                              tuple(_match_tokens(prop, value, lookup))))
        for prop in RAW_PROPS:
            if prop in b or not _present(n, prop):
                continue
            value = _value_of(n, prop)
            if value is not None:
                raw.append((prop, value, tuple(_match_tokens(prop, value, lookup))))
        for c in n.get("children", []):
            walk(c)

    walk(doc)

    def render(m, prop):
        if m:
            return " / ".join(f"{prefix}{x}" for x in m)
        if not lookup:
            return "(raw — no token scale)" if tokens_declared_none() \
                else "(no token scale recorded — see --doctor)"
        if not scale_covers(prop, lookup):
            return f"(no {PROP_CATEGORY.get(prop, prop)} scale — write raw)"
        return "** NOT ON THE SCALE **"

    def grouped(rows) -> list:
        by = collections.OrderedDict()
        for prop, item in rows:
            by.setdefault(prop, []).append(item)
        out = []
        for prop, items in by.items():
            out.extend(textwrap.wrap(f"{prop}: " + " | ".join(items), width=118,
                                     subsequent_indent="    ", break_long_words=False,
                                     break_on_hyphens=False))
        return out

    out = ["# hidden subtrees (visible=false or opacity=0) are excluded",
           f"# {doc.get('name')} — every concrete value in the frame, by property",
           f"## bound to a Figma variable ({len(set(bound))} distinct) — these MUST be written as "
           f"tokens; that is what the binding means"]
    if bound:
        out += grouped((prop, f"{value}{f' ({name})' if name != '?' else ''} -> {render(m, prop)}")
                       for name, prop, value, m in sorted(set(bound), key=lambda r: (r[1], r[2])))
    else:
        out.append("## none — this design uses raw values throughout")
    out.append(f"## not bound ({len(set(raw))} distinct) — raw in the design: reproduce exactly; "
               f"use a local token where one matches, flag a miss on a variable-driven design")
    out += grouped((prop, f"{value} -> {render(m, prop)}")
                   for prop, value, m in sorted(set(raw), key=lambda r: (r[0], r[1])))
    return "\n".join(out) + "\n"


# --- variable dictionary ----------------------------------------------------

# Figma variable NAMES are the one thing REST will not serve (/variables/local is 403 without the
# `file_variables:read` scope). The MCP's get_variable_defs has them, but it is metered — so we buy
# each name exactly once. get_variable_defs returns name->value with no ids; boundVariables gives
# id+property with no names. Matching them on value, constrained by what kind of property it is,
# recovers id->name. That dictionary is cumulative, so a variable seen in any earlier frame is
# already known and costs nothing.

# A Figma name is only a candidate for a property if it lives in the matching part of the namespace.
# Without this, #0a0a0a matches both `color/text/primary` and `color/primary`.
NAME_SHAPE = {
    "fills": ("color/text/", "color/background/", "color/"),
    "strokes": ("color/border/",),
    "paddingLeft": ("space-", "gap/"), "paddingRight": ("space-", "gap/"),
    "paddingTop": ("space-", "gap/"), "paddingBottom": ("space-", "gap/"),
    "itemSpacing": ("space-", "gap/"), "counterAxisSpacing": ("space-", "gap/"),
    "size": ("size-",), "width": ("size-",), "height": ("size-",),
    "rectangleCornerRadii": ("border/radius/",), "cornerRadius": ("border/radius/",),
    "strokeWeight": ("border/width/",),
}
# Typography variables are leaf-named by role rather than namespaced by it.
NAME_SUFFIX = {
    "fontSize": "font-size", "lineHeight": "line-height",
    "fontWeight": "font-weight", "fontFamily": "font-family",
    "letterSpacing": "letter-spacing",
}


def attempted_path() -> pathlib.Path:
    return dict_path().with_name("unresolved.json")


def read_attempted() -> dict:
    """Ids a defs payload has already been matched against without producing a single name.
    Recording them is what keeps --vars from demanding an MCP call that cannot help: two
    variables holding the same value in the same namespace stay ambiguous however often
    get_variable_defs is fetched."""
    p = attempted_path()

    return json.loads(p.read_text()) if p.exists() else {}


def read_dict() -> dict:
    p = dict_path()
    return json.loads(p.read_text()) if p.exists() else {}


def _norm(v):
    return v[:-2] if isinstance(v, str) and v.endswith("px") else v


def _bindings(doc: dict) -> list:
    """(variableId, property, resolved value, node type) for every bound property in the frame."""
    out = []

    def walk(n):
        for prop, ref in n.get("boundVariables", {}).items():
            ids = []
            if isinstance(ref, dict) and "id" in ref:
                ids = [ref["id"]]
            elif isinstance(ref, dict):
                ids = [a["id"] for a in ref.values() if isinstance(a, dict) and "id" in a]
            elif isinstance(ref, list):
                ids = [a["id"] for a in ref if isinstance(a, dict) and "id" in a]
            value = _value_of(n, prop)
            for vid in ids:
                out.append((vid, prop, value, n))
        for c in n.get("children", []):
            walk(c)

    walk(doc)
    return out


# A text style's value is a composite that literally names its leaf variables, e.g.
#   Typography/Body2 -> Font(family: "body/body2/font-family", size: body/body2/font-size, ...)
# so a text node carrying that style resolves its typography bindings with no guessing.
FONT_ROLE = {
    "fontFamily": "family", "fontSize": "size", "fontWeight": "weight",
    "lineHeight": "lineHeight", "letterSpacing": "letterSpacing",
}


def _font_parts(composite: str, defs: dict) -> dict:
    parts = {}
    for role, raw in re.findall(r'(\w+):\s*("[^"]*"|[^,)]+)', composite):
        name = raw.strip().strip('"')
        if name in defs:
            parts[role] = name
    return parts


def _candidates(prop: str, value, node: dict, defs: dict, styles: dict) -> list:
    node_type = node.get("type", "")
    if prop in FONT_ROLE:
        style_name = styles.get(node.get("styles", {}).get("text", ""))
        composite = defs.get(style_name or "", "")
        if composite.startswith("Font("):
            named = _font_parts(composite, defs).get(FONT_ROLE[prop])
            if named:
                return [named]
    if value is None:
        return []
    target = str(_norm(value)).lower()
    hits = [n for n, v in defs.items() if str(v).lower() == target]
    if prop in NAME_SUFFIX:
        hits = [n for n in hits if n.lower().endswith(NAME_SUFFIX[prop])]
    elif prop in NAME_SHAPE:
        shapes = NAME_SHAPE[prop]
        if prop == "fills":
            # a fill on a text node is a text colour; on a container it is a background
            shapes = ("color/text/",) if node_type == "TEXT" else ("color/background/",)
            narrowed = [n for n in hits if n.startswith(shapes)]
            hits = narrowed or [n for n in hits if n.startswith("color/")]
        elif prop == "strokes":
            hits = [n for n in hits if n.startswith("color/border/")] or \
                   [n for n in hits if n.startswith("color/")]
        else:
            hits = [n for n in hits if n.startswith(shapes)]
    return sorted(set(hits))


def vars_status(node_id: str) -> None:
    """How much of this frame's variable usage the dictionary already covers, and — of the rest —
    how much a fresh get_variable_defs could actually resolve."""
    doc = document(node_id)
    known = read_dict()
    attempted = read_attempted()
    ids = {vid for vid, *_ in _bindings(doc)}
    named = ids & set(known)
    stuck = sorted((ids - named) & set(attempted))
    fresh = sorted(ids - named - set(stuck))

    print(f"# {doc.get('name')} — {len(ids)} variables used, {len(named)} named")

    if not ids:
        print("# this design binds no variables — nothing to name, and no MCP call to make.")
        print("# every value is raw; --tokens lists them all.")

        return

    if stuck:
        print(f"# {len(stuck)} already looked up and unresolvable — ANOTHER MCP CALL WILL NOT HELP:")
        for vid in stuck:
            rec = attempted[vid]
            detail = " | ".join(rec.get("candidates") or []) or "no candidate matched"
            print(f"    {vid}  {rec.get('prop')}={rec.get('value')}  -> {detail}")
        print("#   treat these like any value the frame will not settle: decide, and say so.")

    if not fresh:
        print("# nothing left to buy: make NO MCP call for this frame.")

        return

    print(f"# {len(fresh)} never looked up -> spend ONE get_variable_defs call, then:")
    print(f"#   figma_fetch.py --vars-merge {node_id} <defs.json>")
    for vid in fresh:
        print(f"    {vid}")


def vars_merge(node_id: str, defs_path: str) -> None:
    """Fold one get_variable_defs payload into the cumulative id->name dictionary."""
    doc = document(node_id)
    # `-` reads stdin, so the payload can be piped in a heredoc instead of written to a file first.
    defs = json.loads(sys.stdin.read() if defs_path == "-" else pathlib.Path(defs_path).read_text())
    known = read_dict()
    resolved, ambiguous, unresolved = 0, [], []
    styles = styles_map(node_id)
    for vid, prop, value, node in _bindings(doc):
        if vid in known:
            continue
        hits = _candidates(prop, value, node, defs, styles)
        if len(hits) == 1:
            known[vid] = hits[0]
            resolved += 1
        elif hits:
            ambiguous.append((vid, prop, value, tuple(hits)))
        else:
            unresolved.append((vid, prop, value))
    dict_path().write_text(json.dumps(dict(sorted(known.items())), indent=1))

    # Remember the ids this payload could not pin down, so a later --vars does not ask for a
    # second call that would produce the same ambiguity.
    attempted = read_attempted()
    for vid, prop, value, hits in ambiguous:
        attempted[vid] = {"status": "ambiguous", "prop": prop, "value": value,
                          "candidates": list(hits)}
    for vid, prop, value in unresolved:
        attempted.setdefault(vid, {"status": "unresolved", "prop": prop, "value": value,
                                   "candidates": []})
    for vid in known:
        attempted.pop(vid, None)
    attempted_path().write_text(json.dumps(dict(sorted(attempted.items())), indent=1))

    print(f"resolved {resolved} new -> {dict_path()} now holds {len(known)}")
    if attempted:
        print(f"{len(attempted)} unresolvable recorded -> {attempted_path()}")
    for vid, prop, value, hits in sorted(set(ambiguous)):
        print(f"  ambiguous  {vid}  {prop}={value}  -> {' | '.join(hits)}")
    for vid, prop, value in sorted(set(unresolved)):
        print(f"  unresolved {vid}  {prop}={value}")


# --- DOM diff ---------------------------------------------------------------

# measure.js (beside this script) reports every target's box and computed styles in one browser
# call. This side computes the same numbers from the frame and prints them side by side, so the
# verification round is two calls: one measure, one diff — not one getBoundingClientRect per node.

TOL = 0.5  # px; anything under this is sub-pixel rounding, not a defect


def _index(doc: dict) -> dict:
    idx = {}

    def walk(n):
        idx[n["id"]] = n
        for c in n.get("children", []):
            walk(c)

    walk(doc)
    return idx


def _num(v):
    """'12px' -> 12.0, 12 -> 12.0, 'normal'/None -> None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.match(r"\s*(-?[\d.]+)", str(v))
    return float(m.group(1)) if m else None


def _frame_values(n: dict) -> dict:
    """What the frame states for this node, keyed the way measure.js keys the DOM."""
    want = {}
    if n.get("layoutMode"):
        for k in ("paddingTop", "paddingRight", "paddingBottom", "paddingLeft"):
            want[k] = float(n.get(k) or 0)
        want["columnGap" if n["layoutMode"] == "HORIZONTAL" else "rowGap"] = float(n.get("itemSpacing") or 0)
    radii = n.get("rectangleCornerRadii")
    if radii and len(set(radii)) > 1:
        want["radii"] = [float(r) for r in radii]
    elif isinstance(n.get("cornerRadius"), (int, float)):
        want["borderRadius"] = float(n["cornerRadius"])
    if _present(n, "strokes"):
        want["borderColor"] = _value_of(n, "strokes")
        want["borderWidth"] = float(n.get("strokeWeight") or 1)
    if _present(n, "fills"):
        want["color" if n.get("type") == "TEXT" else "backgroundColor"] = _value_of(n, "fills")
    st = n.get("style") or {}
    if st.get("fontSize"):
        want["fontSize"] = float(st["fontSize"])
    if st.get("fontWeight"):
        want["fontWeight"] = float(st["fontWeight"])
    if st.get("lineHeightPx"):
        want["lineHeight"] = float(st["lineHeightPx"])
    if st.get("letterSpacing"):
        want["letterSpacing"] = float(st["letterSpacing"])
    if n.get("opacity") is not None and n["opacity"] != 1:
        want["opacity"] = float(n["opacity"])
    return want


def diff(node_id: str, path: str, show_all: bool = False) -> None:
    measured = json.loads(sys.stdin.read() if path == "-" else pathlib.Path(path).read_text())
    if measured.get("error"):
        sys.exit(f"measure.js: {measured['error']}")
    doc = document(node_id)
    idx = _index(doc)
    rb = doc["absoluteBoundingBox"]
    targets = measured.get("targets", measured)
    rows, skipped = [], []

    for raw_id, dom in targets.items():
        nid = raw_id.replace("-", ":")
        n = idx.get(nid)
        if n is None:
            skipped.append((nid, "not in this frame"))
            continue
        if not dom:
            skipped.append((nid, "selector matched nothing"))
            continue
        name = n.get("name", "")
        want = {}
        bb = n.get("absoluteBoundingBox")
        if bb:
            want.update(x=bb["x"] - rb["x"], y=bb["y"] - rb["y"], w=bb["width"], h=bb["height"])
        want.update(_frame_values(n))
        stroke_w = float(n.get("strokeWeight") or 0) if _present(n, "strokes") else 0

        for prop, fv in want.items():
            dv = dom.get(prop)
            note = ""
            if isinstance(fv, str):
                ok = dv is not None and str(dv).lower() == fv.lower()
                delta = "" if ok else ("missing" if dv is None else "differs")
                shown = dv if dv is not None else "—"
            elif isinstance(fv, list):
                dvl = [_num(x) for x in (dv or [])]
                ok = len(dvl) == len(fv) and all(
                    x is not None and abs(x - y) <= TOL for x, y in zip(dvl, fv))
                delta = "" if ok else "differs"
                fv = ",".join(f"{x:g}" for x in fv)
                shown = ",".join("—" if x is None else f"{x:g}" for x in dvl) if dvl else "—"
            else:
                dvn = _num(dv)
                ok = dvn is not None and abs(dvn - fv) <= TOL
                delta = "" if ok else ("missing" if dvn is None else f"{dvn - fv:+.2f}")
                shown = "—" if dvn is None else f"{dvn:g}"
                if not ok and dvn is not None:
                    if prop == "h" and n.get("type") == "TEXT" and dvn > fv:
                        note = "figma trims text boxes; taller in CSS is expected"
                    elif prop in ("w", "h") and stroke_w and abs(abs(dvn - fv) - 2 * stroke_w) <= TOL:
                        note = "figma strokes inside, CSS outside — border width accounts for it"
                fv = f"{fv:g}"
            rows.append((nid, name, prop, fv, shown, delta, ok, note))

    bad = [r for r in rows if not r[6]]
    print(f"# {doc.get('name')} — {len(rows)} values compared across {len(targets) - len(skipped)} "
          f"nodes, {len(bad)} differ (tolerance {TOL}px)")
    if not show_all:
        print(f"# {len(rows) - len(bad)} match and are not listed (--all lists them)")
    print()
    listed = rows if show_all else bad
    if listed:
        print(f"{'node':<14} {'name':<26} {'prop':<16} {'frame':>12} {'dom':>12}  {'Δ':<8} note")
    for nid, name, prop, fv, shown, delta, ok, note in listed:
        mark = "  " if ok else "✗ "
        print(f"{mark}{nid:<12} {name[:26]:<26} {prop:<16} {str(fv):>12} {str(shown):>12}  "
              f"{delta:<8} {note}")
    for nid, why in skipped:
        print(f"?  {nid:<12} {why}")
    if bad:
        print(f"\n{len(bad)} to fix. A note beside a row names a Figma-vs-CSS difference that is "
              f"not a defect — see references/verification.md.")
    elif not skipped:
        print("every measured value matches the frame")


# --- rendered image ---------------------------------------------------------


def image(node_id: str, scale: str = "2") -> None:
    nid = node_id.replace("-", ":")
    out = cache_dir() / f"{node_id.replace(':', '-')}@{scale}x.png"
    # One render per node per scale. The frame does not change mid-round, and a second render is
    # a second image in the conversation for the rest of the session.
    if out.exists():
        print(f"{out}  (cached — already rendered this round; do not read it again)")
        return
    data = _get(
        f"https://api.figma.com/v1/images/{file_key()}"
        f"?ids={nid}&format=png&scale={scale}"
    )
    if data.get("err"):
        sys.exit(f"figma: {data['err']}")
    url = data["images"][nid]
    with urllib.request.urlopen(url, timeout=120) as r:
        out.write_bytes(r.read())
    print(out)


def main() -> None:
    # Flags that take a value consume the next argument, so it is not mistaken for a node.
    VALUED = ("--depth", "--prefix", "--set-tokens")
    flags, opts, args = [], {}, []
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in VALUED:
            opts[a] = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
            continue
        (flags if a.startswith("--") else args).append(a)
        i += 1
    if "--doctor" in flags:
        doctor()
    if "--set-tokens" in opts:
        set_tokens(opts["--set-tokens"], opts.get("--prefix", ""))
        sys.exit(0)
    if not args or "--help" in flags or "-h" in flags:
        sys.exit(__doc__)
    depth = int(opts["--depth"]) if opts.get("--depth") else None
    full = "--full" in flags
    nodes = [parse_node(a) for a in args[:1]] + [parse_node(a) for a in args[1:]
                                                 if a != "-" and not pathlib.Path(a).exists()]
    if "--read" in flags:
        read(nodes[0], depth, full)
    elif "--vars" in flags:
        vars_status(nodes[0])
    elif "--vars-merge" in flags:
        vars_merge(nodes[0], args[1] if len(args) > 1 else "-")
    elif "--diff" in flags:
        diff(nodes[0], args[1] if len(args) > 1 else "-", show_all="--all" in flags)
    elif "--image" in flags:
        image(nodes[0], args[1] if len(args) > 1 else "2")
    elif "--tokens" in flags:
        for nid in nodes:
            tokens(nid)
            print()
    else:
        for nid in nodes:
            table(nid, depth, full)
            print()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # `| head` closed the pipe. Not an error worth a traceback — though it is the pattern
        # SKILL.md says not to use; --read is sized to arrive whole.
        try:
            sys.stdout.close()
        except Exception:
            pass
        os._exit(0)
