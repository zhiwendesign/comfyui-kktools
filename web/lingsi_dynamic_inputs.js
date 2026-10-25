import { app } from "../../scripts/app.js";

const NODE_NAME = "kkGPT-image_API";
const MAX_INPUTS = 9;
const INPUT_GROUPS = [
  {
    type: "STRING",
    names: ["string", ...Array.from({ length: MAX_INPUTS - 1 }, (_, index) => `string_${index + 1}`)],
  },
  {
    type: "IMAGE",
    names: ["image", ...Array.from({ length: MAX_INPUTS - 1 }, (_, index) => `image_${index + 1}`)],
  },
];
const UPDATE_FRAME = Symbol("lingsiDynamicInputs");

function nodeClass(node) {
  return node?.comfyClass || node?.type || node?.constructor?.comfyClass || "";
}

function inputGroup(name) {
  return INPUT_GROUPS.find((group) => group.names.includes(name));
}

function graphLink(node, linkId) {
  const graph = node.graph || app.graph;
  if (!graph || linkId == null) return null;
  return graph.links?.get?.(linkId) || graph.links?.[linkId] || null;
}

function restoreInputLinks(node, linksByName) {
  for (let index = 0; index < (node.inputs || []).length; index += 1) {
    const input = node.inputs[index];
    const link = linksByName.get(input.name);
    if (link) {
      link.target_slot = index;
      if ("targetSlot" in link) link.targetSlot = index;
    }
  }
}

function addGroupInput(node, group, index) {
  const name = group.names[index];
  if (!name || node.inputs?.some((input) => input.name === name)) return false;

  node.addInput(name, group.type);
  const addedIndex = node.inputs.findIndex((input) => input.name === name);
  const [added] = node.inputs.splice(addedIndex, 1);
  let insertAt = node.inputs.length;
  let foundGroup = false;

  for (let slot = 0; slot < node.inputs.length; slot += 1) {
    const current = group.names.indexOf(node.inputs[slot]?.name);
    if (current >= 0) {
      foundGroup = true;
      if (current > index) {
        insertAt = slot;
        break;
      }
    } else if (foundGroup) {
      insertAt = slot;
      break;
    }
  }

  node.inputs.splice(insertAt, 0, added);
  return true;
}

function orderGroupInputs(node, group) {
  const firstGroup = node.inputs.findIndex((input) => group.names.includes(input.name));
  if (firstGroup < 0) return false;

  const insertAt = node.inputs
    .slice(0, firstGroup)
    .filter((input) => !group.names.includes(input.name)).length;
  const groupedInputs = node.inputs
    .filter((input) => group.names.includes(input.name))
    .sort((a, b) => group.names.indexOf(a.name) - group.names.indexOf(b.name));
  const otherInputs = node.inputs.filter((input) => !group.names.includes(input.name));
  const ordered = [
    ...otherInputs.slice(0, insertAt),
    ...groupedInputs,
    ...otherInputs.slice(insertAt),
  ];
  if (ordered.every((input, index) => input === node.inputs[index])) return false;

  node.inputs.splice(0, node.inputs.length, ...ordered);
  return true;
}

function stabilizeInputGroup(node, group) {
  const linksByName = new Map(node.inputs.map((input, index) => [
    input.name,
    node.getInputLink?.(index) || graphLink(node, input.link),
  ]));
  let highestConnected = -1;
  for (let slot = 0; slot < node.inputs.length; slot += 1) {
    const input = node.inputs[slot];
    const index = group.names.indexOf(input.name);
    if (index >= 0 && linksByName.get(input.name)) highestConnected = Math.max(highestConnected, index);
  }

  const visibleCount = Math.min(MAX_INPUTS, Math.max(1, highestConnected + 2));
  let changed = false;
  for (let index = 0; index < visibleCount; index += 1) {
    changed = addGroupInput(node, group, index) || changed;
  }

  const removable = node.inputs
    .map((input, slot) => ({ input, slot, index: group.names.indexOf(input.name) }))
    .filter(({ input, index }) => index >= visibleCount && !linksByName.get(input.name))
    .sort((a, b) => b.slot - a.slot);

  for (const { slot } of removable) {
    node.removeInput(slot);
    changed = true;
  }
  changed = orderGroupInputs(node, group) || changed;
  if (changed) restoreInputLinks(node, linksByName);
  return changed;
}

function stabilizeInputs(node) {
  if (!node?.inputs || node.removed) return;

  let changed = false;
  for (const group of INPUT_GROUPS) changed = stabilizeInputGroup(node, group) || changed;
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
  name: "kktools.lingsi.dynamic-image-inputs",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;

    const changed = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (type, index, connected, linkInfo, ...args) {
      const isDynamicInput = (type === 1 || type === "input") && Boolean(inputGroup(this.inputs?.[index]?.name));
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
    if (nodeClass(node) === NODE_NAME) scheduleStabilize(node);
  },
  loadedGraphNode(node) {
    if (nodeClass(node) === NODE_NAME) scheduleStabilize(node);
  },
});
