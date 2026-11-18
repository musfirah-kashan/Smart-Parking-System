/**
 * Parking Lot Route Visualization – fixed schematic layout
 * Matches the project diagram style (Entrance → A/B/C/D/E/F → slots)
 */
(function () {
  if (!window.ROUTE_GRAPH_DATA) {
    console.warn("ROUTE_GRAPH_DATA not found");
    return;
  }

  const data = window.ROUTE_GRAPH_DATA;
  const { dij_path: dijPath, bfs_path: bfsPath, target, edges: edgeList, nodes: nodeList } = data;

  // Fixed positions matching the classic parking-lot diagram
  const POS = {
    Entrance: { x: 80,  y: 160 },
    A:        { x: 250, y: 70  },
    B:        { x: 420, y: 70  },
    D:        { x: 580, y: 70  },
    C:        { x: 250, y: 250 },
    E:        { x: 420, y: 180 },
    F:        { x: 420, y: 280 },
  };

  // Slot attachment points under sections
  const SLOT_OFFSET = {
    D: { x: 580, y: 160 },
    E: { x: 520, y: 260 },
    F: { x: 480, y: 360 },
  };

  // Build quick lookup: which section owns each slot
  const slotSection = {};
  edgeList.forEach(e => {
    if (["D", "E", "F"].includes(e.from) && !POS[e.to]) slotSection[e.to] = e.from;
    if (["D", "E", "F"].includes(e.to) && !POS[e.from]) slotSection[e.from] = e.to;
  });

  // Place slots near their section (spread them a bit)
  const slotPos = {};
  const sectionSlots = { D: [], E: [], F: [] };
  nodeList.forEach(n => {
    if (n.kind === "slot") {
      const sec = slotSection[n.id] || "D";
      sectionSlots[sec].push(n.id);
    }
  });
  Object.keys(sectionSlots).forEach(sec => {
    const list = sectionSlots[sec];
    list.forEach((id, i) => {
      const base = SLOT_OFFSET[sec] || { x: 500, y: 300 };
      slotPos[id] = {
        x: base.x + (i % 3) * 70 - 30,
        y: base.y + Math.floor(i / 3) * 55
      };
    });
  });

  function getPos(id) {
    return POS[id] || slotPos[id] || { x: 300, y: 300 };
  }

  // Edge key helper
  function edgeKey(a, b) {
    return [a, b].sort().join("|");
  }

  const dijEdges = new Set();
  const bfsEdges = new Set();
  for (let i = 0; i < (dijPath || []).length - 1; i++)
    dijEdges.add(edgeKey(dijPath[i], dijPath[i + 1]));
  for (let i = 0; i < (bfsPath || []).length - 1; i++)
    bfsEdges.add(edgeKey(bfsPath[i], bfsPath[i + 1]));

  // Distance lookup
  const distMap = {};
  edgeList.forEach(e => {
    distMap[edgeKey(e.from, e.to)] = e.distance;
  });

  // Fixed roads (always drawn)
  const FIXED_EDGES = [
    ["Entrance", "A"], ["Entrance", "C"],
    ["A", "B"], ["A", "C"],
    ["B", "D"], ["B", "E"],
    ["C", "F"],
  ];

  // SVG setup
  const W = 720, H = 460;
  const svgNS = "http://www.w3.org/2000/svg";

  function createSVG() {
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", "100%");
    svg.style.display = "block";
    svg.style.background = "#fefaf3";
    return svg;
  }

  function line(svg, x1, y1, x2, y2, color, width, dashed) {
    const l = document.createElementNS(svgNS, "line");
    l.setAttribute("x1", x1); l.setAttribute("y1", y1);
    l.setAttribute("x2", x2); l.setAttribute("y2", y2);
    l.setAttribute("stroke", color);
    l.setAttribute("stroke-width", width);
    l.setAttribute("stroke-linecap", "round");
    if (dashed) l.setAttribute("stroke-dasharray", "8 5");
    svg.appendChild(l);
    return l;
  }

  function text(svg, x, y, str, opts = {}) {
    const t = document.createElementNS(svgNS, "text");
    t.setAttribute("x", x); t.setAttribute("y", y);
    t.setAttribute("text-anchor", opts.anchor || "middle");
    t.setAttribute("dominant-baseline", opts.baseline || "middle");
    t.setAttribute("font-family", "Segoe UI, system-ui, sans-serif");
    t.setAttribute("font-size", opts.size || 12);
    t.setAttribute("font-weight", opts.bold ? "700" : "500");
    t.setAttribute("fill", opts.color || "#334155");
    t.textContent = str;
    svg.appendChild(t);
    return t;
  }

  function circle(svg, x, y, r, fill, stroke, sw) {
    const c = document.createElementNS(svgNS, "circle");
    c.setAttribute("cx", x); c.setAttribute("cy", y);
    c.setAttribute("r", r);
    c.setAttribute("fill", fill);
    c.setAttribute("stroke", stroke);
    c.setAttribute("stroke-width", sw || 2);
    svg.appendChild(c);
    return c;
  }

  function roundedRect(svg, x, y, w, h, rx, fill, stroke) {
    const r = document.createElementNS(svgNS, "rect");
    r.setAttribute("x", x); r.setAttribute("y", y);
    r.setAttribute("width", w); r.setAttribute("height", h);
    r.setAttribute("rx", rx);
    r.setAttribute("fill", fill);
    r.setAttribute("stroke", stroke || "none");
    r.setAttribute("stroke-width", 2);
    svg.appendChild(r);
    return r;
  }

  function draw(mode) {
    const container = document.getElementById("routeGraph");
    if (!container) return;
    container.innerHTML = "";

    const svg = createSVG();
    container.appendChild(svg);

    // --- Draw edges ---
    // 1. All fixed roads (light gray)
    FIXED_EDGES.forEach(([a, b]) => {
      const pa = getPos(a), pb = getPos(b);
      const key = edgeKey(a, b);
      const onDij = dijEdges.has(key);
      const onBfs = bfsEdges.has(key);

      let color = "#94a3b8";
      let width = 3;
      let dashed = false;

      if (mode === "dij" && onDij) { color = "#2563eb"; width = 5; }
      else if (mode === "bfs" && onBfs) { color = "#ea580c"; width = 5; }
      else if (mode === "both") {
        if (onDij && onBfs) { color = "#2563eb"; width = 5; }
        else if (onDij) { color = "#2563eb"; width = 5; }
        else if (onBfs) { color = "#ea580c"; width = 5; dashed = true; }
      }

      line(svg, pa.x, pa.y, pb.x, pb.y, color, width, dashed);

      // distance label
      const mx = (pa.x + pb.x) / 2;
      const my = (pa.y + pb.y) / 2 - 10;
      const d = distMap[key];
      if (d != null) {
        text(svg, mx, my, d + " m", { size: 11, color: "#64748b", bold: true });
      }
    });

    // 2. Slot edges (from section to slot)
    edgeList.forEach(e => {
      if (POS[e.from] && POS[e.to]) return; // already drawn
      const a = e.from, b = e.to;
      const pa = getPos(a), pb = getPos(b);
      const key = edgeKey(a, b);
      const onDij = dijEdges.has(key);
      const onBfs = bfsEdges.has(key);

      let color = "#cbd5e1";
      let width = 2;
      if ((mode === "dij" || mode === "both") && onDij) { color = "#2563eb"; width = 4; }
      if ((mode === "bfs" || mode === "both") && onBfs) { color = "#ea580c"; width = 4; }

      line(svg, pa.x, pa.y, pb.x, pb.y, color, width, false);
      text(svg, (pa.x + pb.x) / 2 + 12, (pa.y + pb.y) / 2, e.distance + " m", { size: 10, color: "#64748b" });
    });

    // --- Draw fixed nodes ---
    const nodeStyle = {
      Entrance: { r: 28, fill: "#fff7ed", stroke: "#ea580c", shape: "rect" },
      A: { r: 22, fill: "#eff6ff", stroke: "#2563eb" },
      B: { r: 22, fill: "#eff6ff", stroke: "#2563eb" },
      C: { r: 22, fill: "#eff6ff", stroke: "#2563eb" },
      D: { r: 22, fill: "#f0fdf4", stroke: "#16a34a" },
      E: { r: 22, fill: "#f0fdf4", stroke: "#16a34a" },
      F: { r: 22, fill: "#f0fdf4", stroke: "#16a34a" },
    };

    Object.keys(POS).forEach(id => {
      const p = POS[id];
      const st = nodeStyle[id] || { r: 20, fill: "#f1f5f9", stroke: "#64748b" };

      if (id === "Entrance") {
        // barrier-style box
        roundedRect(svg, p.x - 42, p.y - 22, 84, 44, 8, "#fff7ed", "#ea580c");
        text(svg, p.x, p.y, "Entrance", { size: 13, bold: true, color: "#9a3412" });
      } else {
        circle(svg, p.x, p.y, st.r, st.fill, st.stroke, 2.5);
        text(svg, p.x, p.y, id, { size: 15, bold: true, color: "#1e293b" });
      }
    });

    // --- Draw slots ---
    nodeList.forEach(n => {
      if (n.kind !== "slot") return;
      const p = getPos(n.id);
      const isTarget = n.id === target;

      // car-like rounded box
      const w = 56, h = 36;
      roundedRect(svg, p.x - w/2, p.y - h/2, w, h, 8,
        isTarget ? "#fee2e2" : "#f1f5f9",
        isTarget ? "#dc2626" : "#94a3b8");

      // small car icon (simple)
      text(svg, p.x, p.y - 6, "🚗", { size: 14 });
      text(svg, p.x, p.y + 12, n.id, {
        size: 11, bold: true,
        color: isTarget ? "#b91c1c" : "#334155"
      });
    });

    // --- Info boxes (BFS / Dijkstra) like the image ---
    // BFS box (orange)
    roundedRect(svg, 20, 340, 210, 95, 10, "#fff7ed", "#fdba74");
    text(svg, 30, 358, "BFS Route", { size: 13, bold: true, color: "#c2410c", anchor: "start" });
    text(svg, 30, 378, "Path: " + (bfsPath || []).join(" → "), { size: 11, color: "#9a3412", anchor: "start" });
    text(svg, 30, 396, "Roads: " + Math.max(0, (bfsPath || []).length - 1), { size: 11, color: "#9a3412", anchor: "start" });
    text(svg, 30, 414, "Total: " + (data.bfs_m || "?") + " m", { size: 12, bold: true, color: "#9a3412", anchor: "start" });

    // Dijkstra box (blue)
    roundedRect(svg, 250, 340, 240, 95, 10, "#eff6ff", "#93c5fd");
    text(svg, 260, 358, "Dijkstra Route", { size: 13, bold: true, color: "#1d4ed8", anchor: "start" });
    text(svg, 260, 378, "Path: " + (dijPath || []).join(" → "), { size: 11, color: "#1e40af", anchor: "start" });
    text(svg, 260, 396, "Total: " + (data.dij_m || "?") + " m", { size: 12, bold: true, color: "#1e40af", anchor: "start" });

    // Target highlight note
    if (target) {
      text(svg, 520, 400, "Target: " + target, { size: 13, bold: true, color: "#b91c1c", anchor: "start" });
    }
  }

  // Button handlers
  window.showRoutePath = function (mode) {
    ["dij", "bfs", "both"].forEach(m => {
      const btn = document.getElementById("btn" + m.charAt(0).toUpperCase() + m.slice(1));
      if (btn) btn.classList.toggle("active", mode === m);
    });
    // fix button ids
    const map = { dij: "btnDij", bfs: "btnBfs", both: "btnBoth" };
    Object.keys(map).forEach(m => {
      const btn = document.getElementById(map[m]);
      if (btn) btn.classList.toggle("active", mode === m);
    });
    draw(mode);
  };

  // Initial
  draw("dij");
})();
