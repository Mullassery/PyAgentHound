(function () {
  const script = document.currentScript;
  const traceId = script.getAttribute("data-trace-id");
  const svg = document.getElementById("graph");
  const detail = document.getElementById("graph-detail");

  const NS = "http://www.w3.org/2000/svg";
  const BOX_W = 160;
  const BOX_H = 40;
  const H_GAP = 24;
  const V_GAP = 70;

  function el(tag, attrs) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  function layout(nodes, edges) {
    const byId = {};
    nodes.forEach((n) => (byId[n.id] = n));
    const outgoing = {};
    edges.forEach((e) => {
      (outgoing[e.source] = outgoing[e.source] || []).push(e.target);
    });

    const root = nodes.find((n) => n.type === "TRACE") || nodes[0];
    const level = {};
    const queue = [[root.id, 0]];
    const seen = new Set([root.id]);
    while (queue.length) {
      const [id, d] = queue.shift();
      level[id] = d;
      (outgoing[id] || []).forEach((next) => {
        if (!seen.has(next)) {
          seen.add(next);
          queue.push([next, d + 1]);
        }
      });
    }
    // any node not reached (shouldn't normally happen) goes on level 0
    nodes.forEach((n) => {
      if (!(n.id in level)) level[n.id] = 0;
    });

    const byLevel = {};
    nodes.forEach((n) => {
      const lvl = level[n.id];
      (byLevel[lvl] = byLevel[lvl] || []).push(n.id);
    });

    const pos = {};
    Object.keys(byLevel)
      .map(Number)
      .sort((a, b) => a - b)
      .forEach((lvl) => {
        const ids = byLevel[lvl];
        const rowWidth = ids.length * BOX_W + (ids.length - 1) * H_GAP;
        ids.forEach((id, i) => {
          pos[id] = {
            x: i * (BOX_W + H_GAP) - rowWidth / 2,
            y: lvl * V_GAP,
          };
        });
      });

    return pos;
  }

  function render(graph) {
    const { nodes, edges } = graph;
    const pos = layout(nodes, edges);

    const xs = Object.values(pos).map((p) => p.x);
    const minX = Math.min(...xs, 0);
    const maxX = Math.max(...xs, 0) + BOX_W;
    const maxY = Math.max(...Object.values(pos).map((p) => p.y), 0) + BOX_H + 20;
    const width = maxX - minX + 40;

    svg.setAttribute("viewBox", `${minX - 20} -20 ${width} ${maxY}`);
    svg.innerHTML = "";

    edges.forEach((e) => {
      const a = pos[e.source];
      const b = pos[e.target];
      if (!a || !b) return;
      const x1 = a.x + BOX_W / 2;
      const y1 = a.y + BOX_H;
      const x2 = b.x + BOX_W / 2;
      const y2 = b.y;
      const midY = (y1 + y2) / 2;
      const path = el("path", {
        class: "edge",
        d: `M${x1},${y1} C${x1},${midY} ${x2},${midY} ${x2},${y2}`,
      });
      if (e.relationship !== "PARENT") path.setAttribute("stroke-dasharray", "4,3");
      svg.appendChild(path);
    });

    nodes.forEach((n) => {
      const p = pos[n.id];
      if (!p) return;
      const g = el("g", { transform: `translate(${p.x},${p.y})` });
      const box = el("rect", {
        class: "node-box",
        width: BOX_W,
        height: BOX_H,
        rx: 6,
      });
      g.appendChild(box);
      const label = el("text", { x: BOX_W / 2, y: 17, "text-anchor": "middle" });
      label.textContent = n.name.length > 20 ? n.name.slice(0, 19) + "…" : n.name;
      g.appendChild(label);
      const typeLabel = el("text", {
        x: BOX_W / 2,
        y: 31,
        "text-anchor": "middle",
        opacity: "0.65",
      });
      typeLabel.textContent = n.type;
      g.appendChild(typeLabel);
      g.addEventListener("click", () => showDetail(n));
      svg.appendChild(g);
    });
  }

  function showDetail(node) {
    const attrs = Object.keys(node.attributes || {})
      .map((k) => `<div><strong>${k}</strong>: ${JSON.stringify(node.attributes[k])}</div>`)
      .join("");
    detail.innerHTML =
      `<strong>${node.name}</strong> (${node.type})` +
      (node.status ? ` — status: ${node.status}` : "") +
      (node.duration_ms != null ? ` — ${node.duration_ms.toFixed(1)}ms` : "") +
      `<div>${attrs || "<em>no attributes</em>"}</div>`;
  }

  fetch(`/api/traces/${traceId}/graph`)
    .then((r) => r.json())
    .then(render)
    .catch(() => {
      detail.textContent = "Failed to load execution graph.";
    });
})();
