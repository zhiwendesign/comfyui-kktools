import { app } from "../../scripts/app.js";

const NODE_NAME = "kkimage2_API";
const MAX_IMAGES = 9;
const IMAGE_NAMES = ["image", ...Array.from({ length: MAX_IMAGES - 1 }, (_, index) => `image_${index + 1}`)];
const UPDATE_FRAME = Symbol("lingsiDynamicImageInputs");

function nodeClass(node) {
  return node?.comfyClass || node?.type || node?.constructor?.comfyClass || "";
}

function imageIndex(name) {
  return IMAGE_NAMES.indexOf(name);
}

function graphLink(node, linkId) {
  const graph = node.graph || app.graph;
  if (!graph || linkId == null) return null;
  return graph.links?.get?.(linkId) || graph.links?.[linkId] || null;
}

function syncTargetSlots(node) {
  for (let index = 0; index < (node.inputs || []).length; index += 1) {
    const link = graphLink(node, node.inputs[index]?.link);
    if (link) link.target_slot = index;
  }
}

function addImageInput(node, index) {
  const name = IMAGE_NAMES[index];
  if (!name || node.inputs?.some((input) => input.name === name)) return false;

  node.addInput(name, "IMAGE");
  const addedIndex = node.inputs.findIndex((input) => input.name === name);
  const [added] = node.inputs.splice(addedIndex, 1);
  let insertAt = node.inputs.length;
  let foundImage = false;

  for (let slot = 0; slot < node.inputs.length; slot += 1) {
    const current = imageIndex(node.inputs[slot]?.name);
    if (current >= 0) {
      foundImage = true;
      if (current > index) {
        insertAt = slot;
        break;
      }
    } else if (foundImage) {
      insertAt = slot;
      break;
    }
  }

  node.inputs.splice(insertAt, 0, added);
  syncTargetSlots(node);
  return true;
}

function orderImageInputs(node) {
  const firstImage = node.inputs.findIndex((input) => imageIndex(input.name) >= 0);
  if (firstImage < 0) return false;

  const insertAt = node.inputs
    .slice(0, firstImage)
    .filter((input) => imageIndex(input.name) < 0).length;
  const images = node.inputs
    .filter((input) => imageIndex(input.name) >= 0)
    .sort((a, b) => imageIndex(a.name) - imageIndex(b.name));
  const otherInputs = node.inputs.filter((input) => imageIndex(input.name) < 0);
  const ordered = [
    ...otherInputs.slice(0, insertAt),
    ...images,
    ...otherInputs.slice(insertAt),
  ];
  if (ordered.every((input, index) => input === node.inputs[index])) return false;

  node.inputs.splice(0, node.inputs.length, ...ordered);
  syncTargetSlots(node);
  return true;
}

function stabilizeImageInputs(node) {
  if (!node?.inputs || node.removed) return;

  let highestConnected = -1;
  for (const input of node.inputs) {
    const index = imageIndex(input.name);
    if (index >= 0 && input.link != null) highestConnected = Math.max(highestConnected, index);
  }

  const visibleCount = Math.min(MAX_IMAGES, Math.max(1, highestConnected + 2));
  let changed = false;
  for (let index = 0; index < visibleCount; index += 1) {
    changed = addImageInput(node, index) || changed;
  }

  const removable = node.inputs
    .map((input, slot) => ({ input, slot, index: imageIndex(input.name) }))
    .filter(({ input, index }) => index >= visibleCount && input.link == null)
    .sort((a, b) => b.slot - a.slot);

  for (const { slot } of removable) {
    node.removeInput(slot);
    changed = true;
  }
  changed = orderImageInputs(node) || changed;

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
    stabilizeImageInputs(node);
  });
}

app.registerExtension({
  name: "kktools.lingsi.dynamic-image-inputs",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;

    const changed = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (type, index, connected, linkInfo, ...args) {
      const isImageInput = (type === 1 || type === "input") && imageIndex(this.inputs?.[index]?.name) >= 0;
      const result = changed?.call(this, type, index, connected, linkInfo, ...args);
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
