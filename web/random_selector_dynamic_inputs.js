import { app } from "../../scripts/app.js";

const NODE_NAMES = new Set(["kkRandomSelector", "kkSwitchCase"]);
const INPUT_NAMES = Array.from({ length: 9 }, (_, index) => `input_${index + 1}`);
const UPDATE_FRAME = Symbol("randomSelectorDynamicInputs");
const HIDDEN_CASE = Symbol("switchCaseHiddenWidget");

function graphLink(node, linkId) {
  const graph = node.graph || app.graph;
  if (!graph || linkId == null) return null;
  return graph.links?.get?.(linkId) || graph.links?.[linkId] || null;
}

function stabilizeInputs(node) {
  if (!node?.inputs || node.removed) return;
  const linksByName = new Map(node.inputs.map((input, index) => [
    input.name,
    node.getInputLink?.(index) || graphLink(node, input.link),
  ]));
  let highestConnected = -1;
  for (const name of INPUT_NAMES) {
    if (linksByName.get(name)) highestConnected = INPUT_NAMES.indexOf(name);
  }

  const visibleCount = Math.min(INPUT_NAMES.length, Math.max(1, highestConnected + 2));
  let changed = false;
  for (let index = 0; index < visibleCount; index += 1) {
    if (!node.inputs.some((input) => input.name === INPUT_NAMES[index])) {
      node.addInput(INPUT_NAMES[index], "*");
      changed = true;
    }
  }
  for (let index = node.inputs.length - 1; index >= 0; index -= 1) {
    const input = node.inputs[index];
    const portIndex = INPUT_NAMES.indexOf(input.name);
    if (portIndex >= visibleCount && !linksByName.get(input.name)) {
      node.removeInput(index);
      changed = true;
    }
  }

  const first = node.inputs.findIndex((input) => INPUT_NAMES.includes(input.name));
  const before = node.inputs.slice(0, first).filter((input) => !INPUT_NAMES.includes(input.name));
  const after = node.inputs.slice(first).filter((input) => !INPUT_NAMES.includes(input.name));
  const ports = node.inputs
    .filter((input) => INPUT_NAMES.includes(input.name))
    .sort((a, b) => INPUT_NAMES.indexOf(a.name) - INPUT_NAMES.indexOf(b.name));
  const ordered = [...before, ...ports, ...after];
  if (ordered.some((input, index) => input !== node.inputs[index])) {
    node.inputs.splice(0, node.inputs.length, ...ordered);
    changed = true;
  }
  if ((node.comfyClass || node.type || node.constructor?.comfyClass) === "kkSwitchCase") {
    for (const widget of node.widgets || []) {
      const match = /^case_([1-9])$/.exec(widget.name);
      if (!match) continue;
      const index = Number(match[1]);
      const linked = linksByName.has(widget.name) && linksByName.get(widget.name);
      if (index > visibleCount && !linked && !widget[HIDDEN_CASE]) {
        widget[HIDDEN_CASE] = { hidden: widget.hidden, computeSize: widget.computeSize };
        widget.hidden = true;
        widget.computeSize = () => [0, -4];
        changed = true;
      } else if ((index <= visibleCount || linked) && widget[HIDDEN_CASE]) {
        widget.hidden = widget[HIDDEN_CASE].hidden;
        widget.computeSize = widget[HIDDEN_CASE].computeSize;
        delete widget[HIDDEN_CASE];
        changed = true;
      }
    }
  }
  if (!changed) return;

  for (let index = 0; index < node.inputs.length; index += 1) {
    const link = linksByName.get(node.inputs[index].name);
    if (!link) continue;
    link.target_slot = index;
    if ("targetSlot" in link) link.targetSlot = index;
  }
  const computed = node.computeSize?.();
  if (computed && node.setSize) node.setSize([Math.max(node.size?.[0] || 0, computed[0]), computed[1]]);
  app.graph?.setDirtyCanvas?.(true, true);
  app.canvas?.setDirty?.(true, true);
}

function scheduleStabilize(node) {
  if (!node || node[UPDATE_FRAME] != null) return;
  node[UPDATE_FRAME] = requestAnimationFrame(() => {
    node[UPDATE_FRAME] = null;
    stabilizeInputs(node);
  });
}

app.registerExtension({
  name: "kktools.random-selector.dynamic-inputs",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (!NODE_NAMES.has(nodeData.name)) return;
    const changed = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (type, index, connected, linkInfo, ...args) {
      const isDynamicInput = (type === 1 || type === "input") && INPUT_NAMES.includes(this.inputs?.[index]?.name);
      const result = changed?.call(this, type, index, connected, linkInfo, ...args);
      if (isDynamicInput) scheduleStabilize(this);
      return result;
    };
    const configured = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const result = configured?.apply(this, args);
      scheduleStabilize(this);
      return result;
    };
  },
  nodeCreated(node) {
    if (NODE_NAMES.has(node?.comfyClass || node?.type || node?.constructor?.comfyClass)) scheduleStabilize(node);
  },
  loadedGraphNode(node) {
    if (NODE_NAMES.has(node?.comfyClass || node?.type || node?.constructor?.comfyClass)) scheduleStabilize(node);
  },
});
