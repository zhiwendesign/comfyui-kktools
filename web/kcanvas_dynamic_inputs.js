import { app } from "../../scripts/app.js";

const NODE_NAME = "kcanvas";
const IMAGE_NAMES = Array.from({ length: 9 }, (_, index) => `image${index + 1}`);
const MASK_NAMES = Array.from({ length: 9 }, (_, index) => `mask${index + 1}`);
const DYNAMIC_INPUT_NAMES = new Set([...IMAGE_NAMES, ...MASK_NAMES]);
const LEGACY_MASK_NAME = "mask";
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

function pairIndex(name) {
  const imageIndex = IMAGE_NAMES.indexOf(name);
  return imageIndex >= 0 ? imageIndex : MASK_NAMES.indexOf(name);
}

function normalizeLegacyMaskInput(node) {
  const legacyIndex = node.inputs?.findIndex((input) => input.name === LEGACY_MASK_NAME) ?? -1;
  if (legacyIndex < 0) return false;
  const currentIndex = node.inputs.findIndex((input) => input.name === MASK_NAMES[0]);
  if (currentIndex < 0) {
    node.inputs[legacyIndex].name = MASK_NAMES[0];
    node.inputs[legacyIndex].type = "MASK";
    return true;
  }

  const legacyInput = node.inputs[legacyIndex];
  const currentInput = node.inputs[currentIndex];
  const legacyLink = node.getInputLink?.(legacyIndex) || graphLink(node, legacyInput.link);
  const currentLink = node.getInputLink?.(currentIndex) || graphLink(node, currentInput.link);
  if (legacyLink && !currentLink) {
    currentInput.link = legacyInput.link;
    legacyInput.link = null;
    legacyLink.target_slot = currentIndex;
    if ("targetSlot" in legacyLink) legacyLink.targetSlot = currentIndex;
  } else if (legacyLink) {
    node.disconnectInput?.(legacyIndex);
  }
  node.removeInput(legacyIndex);
  return true;
}

function removeInvalidLinks(node) {
  let changed = false;
  for (let index = 0; index < (node.inputs || []).length; index += 1) {
    const input = node.inputs[index];
    if (!DYNAMIC_INPUT_NAMES.has(input?.name)) continue;
    const link = node.getInputLink?.(index) || graphLink(node, input.link);
    if (!link) continue;
    const originId = link.origin_id ?? link.originId;
    const originSlot = link.origin_slot ?? link.originSlot;
    const origin = (node.graph || app.graph)?.getNodeById?.(originId);
    const outputType = origin?.outputs?.[originSlot]?.type;
    const expectedType = IMAGE_NAMES.includes(input.name) ? "IMAGE" : "MASK";
    if (outputType && outputType !== expectedType) {
      node.disconnectInput?.(index);
      changed = true;
    }
  }
  return changed;
}

function addPair(node, index) {
  let changed = false;
  const imageName = IMAGE_NAMES[index];
  const maskName = MASK_NAMES[index];
  if (imageName && !node.inputs?.some((input) => input.name === imageName)) {
    node.addInput(imageName, "IMAGE");
    changed = true;
  }
  if (maskName && !node.inputs?.some((input) => input.name === maskName)) {
    node.addInput(maskName, "MASK");
    changed = true;
  }
  return changed;
}

function orderInputs(node) {
  const first = node.inputs.findIndex((input) => DYNAMIC_INPUT_NAMES.has(input.name));
  if (first < 0) return false;
  const linksByName = new Map(node.inputs.map((input, index) => [
    input.name,
    node.getInputLink?.(index) || graphLink(node, input.link),
  ]));
  const pairedInputs = node.inputs
    .filter((input) => DYNAMIC_INPUT_NAMES.has(input.name))
    .sort((a, b) => pairIndex(a.name) - pairIndex(b.name) || (IMAGE_NAMES.includes(a.name) ? -1 : 1));
  const beforePairs = node.inputs
    .slice(0, first)
    .filter((input) => !DYNAMIC_INPUT_NAMES.has(input.name));
  const afterPairs = node.inputs
    .slice(first)
    .filter((input) => !DYNAMIC_INPUT_NAMES.has(input.name));
  const ordered = [...beforePairs, ...pairedInputs, ...afterPairs];
  if (ordered.every((input, index) => input === node.inputs[index])) return false;
  node.inputs.splice(0, node.inputs.length, ...ordered);
  restoreInputLinks(node, linksByName);
  return true;
}

function stabilizeInputs(node) {
  if (!node?.inputs || node.removed) return;
  let changed = normalizeLegacyMaskInput(node);
  changed = removeInvalidLinks(node) || changed;
  const linksByName = new Map(node.inputs.map((input, index) => [
    input.name,
    node.getInputLink?.(index) || graphLink(node, input.link),
  ]));
  let highestConnected = -1;
  for (const input of node.inputs) {
    const index = pairIndex(input.name);
    if (index >= 0 && linksByName.get(input.name)) highestConnected = Math.max(highestConnected, index);
  }

  const visibleCount = Math.min(IMAGE_NAMES.length, Math.max(1, highestConnected + 2));
  for (let index = 0; index < visibleCount; index += 1) changed = addPair(node, index) || changed;

  for (let index = IMAGE_NAMES.length - 1; index >= visibleCount; index -= 1) {
    if (linksByName.get(IMAGE_NAMES[index]) || linksByName.get(MASK_NAMES[index])) continue;
    const slots = node.inputs
      .map((input, slot) => ({ name: input.name, slot }))
      .filter(({ name }) => name === IMAGE_NAMES[index] || name === MASK_NAMES[index])
      .sort((a, b) => b.slot - a.slot);
    for (const { slot } of slots) {
      node.removeInput(slot);
      changed = true;
    }
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
      const isDynamicInput = (type === 1 || type === "input") && DYNAMIC_INPUT_NAMES.has(this.inputs?.[index]?.name);
      const result = connectionsChanged?.call(this, type, index, connected, linkInfo, ...args);
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
    if (nodeClass(node) === NODE_NAME) scheduleStabilize(node);
  },
  loadedGraphNode(node) {
    if (nodeClass(node) === NODE_NAME) scheduleStabilize(node);
  },
});
