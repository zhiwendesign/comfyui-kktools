import { app } from "../../scripts/app.js";

const LEGACY_INPUTS = {
  ImagenStudioTemplateDistiller: {
    images: "参考图像",
  },
  ImagenStudioTemplateComposer: {
    template_json: "模板JSON",
    reference_images: "参考图像",
  },
  ImagenStudioRunningHubRHArtG2: {
    prompt: "正向提示词",
  },
};

function getNodeClass(node) {
  return node?.comfyClass || node?.type || node?.constructor?.comfyClass || "";
}

function getGraphLink(graph, linkId) {
  if (!graph || linkId == null) {
    return null;
  }
  if (graph.links?.get) {
    return graph.links.get(linkId) || null;
  }
  return graph.links?.[linkId] || null;
}

function findInputIndex(node, name) {
  return node.inputs?.findIndex((input) => input?.name === name) ?? -1;
}

function moveLinkToInput(node, linkId, inputName) {
  const targetIndex = findInputIndex(node, inputName);
  if (targetIndex < 0 || linkId == null) {
    return;
  }
  const link = getGraphLink(node.graph || app.graph, linkId);
  if (link) {
    link.target_slot = targetIndex;
  }
  node.inputs[targetIndex].link = linkId;
}

function removeInputSlot(node, index) {
  if (typeof node.removeInput === "function") {
    node.removeInput(index);
  } else if (node.inputs) {
    node.inputs.splice(index, 1);
  }
}

function cleanupLegacyInputs(node) {
  const mapping = LEGACY_INPUTS[getNodeClass(node)];
  if (!mapping || !node?.inputs?.length) {
    return;
  }

  let changed = false;

  for (const [legacyName, targetName] of Object.entries(mapping)) {
    let legacyIndex = findInputIndex(node, legacyName);
    while (legacyIndex >= 0) {
      const targetIndex = findInputIndex(node, targetName);
      const legacyInput = node.inputs[legacyIndex];
      const linkId = legacyInput?.link;
      const targetHasLink = targetIndex >= 0 && node.inputs[targetIndex]?.link != null;

      if (targetIndex >= 0 && linkId != null && !targetHasLink) {
        legacyInput.link = null;
        removeInputSlot(node, legacyIndex);
        moveLinkToInput(node, linkId, targetName);
      } else {
        if (linkId != null && typeof node.disconnectInput === "function") {
          node.disconnectInput(legacyIndex);
        }
        removeInputSlot(node, legacyIndex);
      }

      changed = true;
      legacyIndex = findInputIndex(node, legacyName);
    }
  }

  if (changed) {
    if (typeof node.computeSize === "function" && typeof node.setSize === "function") {
      node.setSize(node.computeSize());
    }
    app.graph?.setDirtyCanvas?.(true, true);
    app.canvas?.setDirty?.(true, true);
  }
}

function cleanupSoon(node) {
  cleanupLegacyInputs(node);
  requestAnimationFrame(() => {
    cleanupLegacyInputs(node);
  });
}

app.registerExtension({
  name: "ImagenStudio.CleanupLegacyInputs",
  nodeCreated(node) {
    cleanupSoon(node);
  },
  loadedGraphNode(node) {
    cleanupSoon(node);
  },
});
