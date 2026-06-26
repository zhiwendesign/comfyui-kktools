import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const STATUS_EVENT = "imagen-studio/status";
const STATUS_NODE_CLASSES = new Set([
  "ImagenStudioPPTPageComposer",
  "ImagenStudioPPTRunningHubBatch",
]);
const STYLE_ID = "imagen-studio-status-style";

function nodeClass(node) {
  return node?.comfyClass || node?.type || node?.constructor?.comfyClass || "";
}

function addStyles() {
  if (document.getElementById(STYLE_ID)) {
    return;
  }
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .imagen-status {
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      gap: 6px;
      width: 100%;
      min-height: 54px;
      padding: 8px 10px;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      background: rgba(20, 20, 20, 0.24);
      color: var(--fg-color);
      font-size: 12px;
      line-height: 1.35;
      overflow: hidden;
    }
    .imagen-status__top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      min-width: 0;
    }
    .imagen-status__label {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--descrip-text);
    }
    .imagen-status__count {
      flex: 0 0 auto;
      color: var(--descrip-text);
      font-variant-numeric: tabular-nums;
    }
    .imagen-status__message {
      min-height: 16px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .imagen-status__bar {
      position: relative;
      height: 4px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.12);
    }
    .imagen-status__fill {
      width: 0%;
      height: 100%;
      border-radius: inherit;
      background: #4aa3ff;
      transition: width 160ms ease, background 160ms ease;
    }
    .imagen-status[data-level="success"] .imagen-status__fill { background: #45d483; }
    .imagen-status[data-level="warning"] .imagen-status__fill { background: #f3b44b; }
    .imagen-status[data-level="error"] .imagen-status__fill { background: #ff5c5c; }
    .imagen-status[data-level="running"] .imagen-status__fill { background: #4aa3ff; }
  `;
  document.head.appendChild(style);
}

function getGraphNodes() {
  return app.graph?._nodes || app.graph?.nodes || [];
}

function matchesPayload(node, payload) {
  const klass = nodeClass(node);
  if (!STATUS_NODE_CLASSES.has(klass)) {
    return false;
  }
  const payloadNodeId = payload?.node_id == null ? "" : String(payload.node_id);
  if (payloadNodeId) {
    return String(node.id) === payloadNodeId;
  }
  return !payload?.node_class || payload.node_class === klass;
}

function renderStatus(node, payload) {
  const state = node.__imagenStatusState;
  if (!state) {
    return;
  }
  const current = Math.max(0, Number(payload?.current || 0));
  const total = Math.max(1, Number(payload?.total || 1));
  const percent = Math.max(0, Math.min(100, Math.round((current / total) * 100)));
  state.root.dataset.level = payload?.level || "info";
  state.label.textContent = payload?.stage ? `状态：${payload.stage}` : "状态";
  state.count.textContent = `${current}/${total}`;
  state.message.textContent = payload?.message || "等待执行";
  state.fill.style.width = `${percent}%`;
  node.setDirtyCanvas?.(true, true);
  app.canvas?.setDirty?.(true, true);
}

function resetStatus(node) {
  renderStatus(node, {
    stage: "idle",
    message: "等待执行",
    current: 0,
    total: 1,
    level: "info",
  });
}

function setupStatusWidget(node) {
  if (node.__imagenStatusWidget || !STATUS_NODE_CLASSES.has(nodeClass(node)) || typeof node.addDOMWidget !== "function") {
    return;
  }
  addStyles();
  const root = document.createElement("div");
  root.className = "imagen-status";
  root.dataset.level = "info";

  const top = document.createElement("div");
  top.className = "imagen-status__top";
  const label = document.createElement("div");
  label.className = "imagen-status__label";
  const count = document.createElement("div");
  count.className = "imagen-status__count";
  top.append(label, count);

  const message = document.createElement("div");
  message.className = "imagen-status__message";
  const bar = document.createElement("div");
  bar.className = "imagen-status__bar";
  const fill = document.createElement("div");
  fill.className = "imagen-status__fill";
  bar.append(fill);
  root.append(top, message, bar);
  root.addEventListener("mousedown", (event) => event.stopPropagation());
  root.addEventListener("wheel", (event) => event.stopPropagation());

  node.__imagenStatusState = { root, label, count, message, fill };
  node.__imagenStatusWidget = node.addDOMWidget("运行状态", "imagen-status", root, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => 58,
    getMaxHeight: () => 70,
  });
  resetStatus(node);
}

function setupSoon(node) {
  setupStatusWidget(node);
  requestAnimationFrame(() => setupStatusWidget(node));
}

api.addEventListener(STATUS_EVENT, (event) => {
  const payload = event.detail || {};
  for (const node of getGraphNodes()) {
    if (matchesPayload(node, payload)) {
      renderStatus(node, payload);
    }
  }
});

api.addEventListener("executing", (event) => {
  const nodeId = event.detail?.node || event.detail;
  if (nodeId == null) {
    return;
  }
  for (const node of getGraphNodes()) {
    if (String(node.id) === String(nodeId) && STATUS_NODE_CLASSES.has(nodeClass(node))) {
      resetStatus(node);
    }
  }
});

app.registerExtension({
  name: "ImagenStudio.Status",
  nodeCreated(node) {
    setupSoon(node);
  },
  loadedGraphNode(node) {
    setupSoon(node);
  },
});
