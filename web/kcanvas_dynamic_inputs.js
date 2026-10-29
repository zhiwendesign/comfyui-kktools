import { app } from "../../scripts/app.js";

const NODE_NAME = "kcanvas";
const INPUT_NAMES = Array.from({ length: 9 }, (_, index) => `image${index + 1}`);
const UPDATE_FRAME = Symbol("kcanvasDynamicInputs");

function nodeClass(node) {
  return node?.comfyClass || node?.type || node?.constructor?.comfyClass || "";
}

function graphLink(node, linkId) {
  const graph = node.graph || app.graph;
  if (!graph || linkId == null) return null;
  return graph.links?.get?.(linkId) || graph.links?.[linkId] || null;
}

function restoreInputLinks(node, linksByName) {
  for (let index = 0; index < (node.inputs || []).length; index += 1) {
    const link = linksByName.get(node.inputs[index].name);
    if (!link) continue;
    link.target_slot = index;
    if ("targetSlot" in link) link.targetSlot = index;
  }
}

function removeInvalidLinks(node) {
  let changed = false;
  for (let index = 0; index < (node.inputs || []).length; index += 1) {
    const input = node.inputs[index];
    if (!INPUT_NAMES.includes(input?.name)) continue;
    const link = node.getInputLink?.(index) || graphLink(node, input.link);
    if (!link) continue;
    const originId = link.origin_id ?? link.originId;
    const originSlot = link.origin_slot ?? link.originSlot;
    const origin = (node.graph || app.graph)?.getNodeById?.(originId);
    const outputType = origin?.outputs?.[originSlot]?.type;
    if (outputType && outputType !== "IMAGE") {
      node.disconnectInput?.(index);
      changed = true;
    }
  }
  return changed;
}

function addInput(node, index) {
  const name = INPUT_NAMES[index];
  if (!name || node.inputs?.some((input) => input.name === name)) return false;
  node.addInput(name, "IMAGE");
  return true;
}

function orderInputs(node) {
  const first = node.inputs.findIndex((input) => INPUT_NAMES.includes(input.name));
  if (first < 0) return false;
  const linksByName = new Map(node.inputs.map((input, index) => [
    input.name,
    node.getInputLink?.(index) || graphLink(node, input.link),
  ]));
  const imageInputs = node.inputs
    .filter((input) => INPUT_NAMES.includes(input.name))
    .sort((a, b) => INPUT_NAMES.indexOf(a.name) - INPUT_NAMES.indexOf(b.name));
  const otherInputs = node.inputs.filter((input) => !INPUT_NAMES.includes(input.name));
  const ordered = [...otherInputs.slice(0, first), ...imageInputs, ...otherInputs.slice(first)];
  if (ordered.every((input, index) => input === node.inputs[index])) return false;
  node.inputs.splice(0, node.inputs.length, ...ordered);
  restoreInputLinks(node, linksByName);
  return true;
}

function stabilizeInputs(node) {
  if (!node?.inputs || node.removed) return;
  let changed = removeInvalidLinks(node);
  const linksByName = new Map(node.inputs.map((input, index) => [
    input.name,
    node.getInputLink?.(index) || graphLink(node, input.link),
  ]));
  let highestConnected = -1;
  for (const input of node.inputs) {
    const index = INPUT_NAMES.indexOf(input.name);
    if (index >= 0 && linksByName.get(input.name)) highestConnected = Math.max(highestConnected, index);
  }

  const visibleCount = Math.min(INPUT_NAMES.length, Math.max(1, highestConnected + 2));
  for (let index = 0; index < visibleCount; index += 1) changed = addInput(node, index) || changed;

  const removable = node.inputs
    .map((input, slot) => ({ input, slot, index: INPUT_NAMES.indexOf(input.name) }))
    .filter(({ input, index }) => index >= visibleCount && !linksByName.get(input.name))
    .sort((a, b) => b.slot - a.slot);
  for (const { slot } of removable) {
    node.removeInput(slot);
    changed = true;
  }
  changed = orderInputs(node) || changed;
  if (!changed) return;

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
  name: "kktools.kcanvas.dynamic-image-inputs",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;

    const connectionsChanged = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (type, index, connected, linkInfo, ...args) {
      const isImageInput = (type === 1 || type === "input") && INPUT_NAMES.includes(this.inputs?.[index]?.name);
      const result = connectionsChanged?.call(this, type, index, connected, linkInfo, ...args);
      if (isImageInput) scheduleStabilize(this);
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
    if (nodeClass(node) === NODE_NAME) scheduleStabilize(node);
  },
  loadedGraphNode(node) {
    if (nodeClass(node) === NODE_NAME) scheduleStabilize(node);
  },
});
