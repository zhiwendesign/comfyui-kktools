import { app } from "../../scripts/app.js";

const NODE_NAME = "kkColorPicker";

function hsvToHex(hue, saturation, value) {
  const chroma = value * saturation;
  const segment = hue / 60;
  const middle = chroma * (1 - Math.abs((segment % 2) - 1));
  const levels = [
    [chroma, middle, 0], [middle, chroma, 0], [0, chroma, middle],
    [0, middle, chroma], [middle, 0, chroma], [chroma, 0, middle],
  ][Math.floor(segment) % 6];
  return "#" + levels.map((level) =>
    Math.round((level + value - chroma) * 255).toString(16).padStart(2, "0")
  ).join("").toUpperCase();
}

function hexToHsv(hex, previousHue) {
  const channels = [1, 3, 5].map((index) => parseInt(hex.slice(index, index + 2), 16) / 255);
  const [red, green, blue] = channels;
  const max = Math.max(...channels);
  const delta = max - Math.min(...channels);
  let hue = previousHue;
  if (delta) {
    if (max === red) hue = ((green - blue) / delta) % 6;
    else if (max === green) hue = (blue - red) / delta + 2;
    else hue = (red - green) / delta + 4;
    hue = (hue * 60 + 360) % 360;
  }
  return { hue, saturation: max ? delta / max : 0, value: max };
}

function setupPicker(node) {
  if (node.__kkColorPicker) return;
  const colorWidget = node.widgets?.find((widget) => widget.name === "color");
  if (!colorWidget || !node.addDOMWidget) return;

  const root = document.createElement("div");
  root.style.cssText = "box-sizing:border-box;display:flex;flex-direction:column;gap:8px;width:100%;height:100%;padding:4px 0 7px;";
  const styles = document.createElement("style");
  styles.textContent = `
    .kk-color-hue { appearance: none; -webkit-appearance: none; }
    .kk-color-hue::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 14px; height: 14px; border-radius: 50%;
      background: white; border: 1px solid #555; cursor: pointer;
    }
    .kk-color-hue::-moz-range-thumb {
      width: 14px; height: 14px; border-radius: 50%;
      background: white; border: 1px solid #555; cursor: pointer;
    }
  `;
  const palette = document.createElement("div");
  palette.tabIndex = 0;
  palette.setAttribute("role", "slider");
  palette.setAttribute("aria-label", "颜色饱和度与明度，使用方向键调整");
  palette.style.cssText = "position:relative;flex:1;min-height:90px;border-radius:6px;cursor:crosshair;touch-action:none;outline-offset:2px;";
  const marker = document.createElement("div");
  marker.style.cssText = "position:absolute;width:14px;height:14px;border:2px solid white;border-radius:50%;box-shadow:0 0 2px 1px #0009;transform:translate(-50%,-50%);pointer-events:none;box-sizing:border-box;";
  palette.appendChild(marker);
  const hueSlider = document.createElement("input");
  hueSlider.type = "range";
  hueSlider.min = "0";
  hueSlider.max = "359";
  hueSlider.step = "1";
  hueSlider.className = "kk-color-hue";
  hueSlider.setAttribute("aria-label", "色相");
  hueSlider.style.cssText = "flex:1;min-width:0;height:14px;margin:0;cursor:pointer;background:linear-gradient(to right,red,#ff0,#0f0,#0ff,#00f,#f0f,red);border-radius:8px;touch-action:none;";
  const hueRow = document.createElement("div");
  hueRow.style.cssText = "display:flex;align-items:center;width:100%;height:18px;flex:none;";
  hueRow.append(hueSlider);
  const swatches = document.createElement("div");
  swatches.style.cssText = "position:relative;width:100%;height:18px;flex:none;";
  root.append(styles, palette, hueRow, swatches);
  let hue = 0;
  let saturation = 1;
  let brightness = 1;
  let updatingPicker = false;

  const paint = () => {
    palette.style.background = `linear-gradient(to top,#000,transparent),linear-gradient(to right,#fff,hsl(${hue} 100% 50%))`;
    marker.style.left = `${saturation * 100}%`;
    marker.style.top = `${(1 - brightness) * 100}%`;
    hueSlider.value = String(Math.round(hue) % 360);
    palette.setAttribute("aria-valuetext", `饱和度 ${Math.round(saturation * 100)}%，明度 ${Math.round(brightness * 100)}%`);
  };

  const syncPicker = () => {
    const value = String(colorWidget.value || "").trim();
    const hex = value.startsWith("#") ? value : `#${value}`;
    if (!/^#[0-9a-f]{6}$/i.test(hex)) return;
    const hsv = hexToHsv(hex, hue);
    hue = hsv.hue;
    saturation = hsv.saturation;
    brightness = hsv.value;
    paint();
  };
  const applyColor = () => {
    const value = hsvToHex(hue, saturation, brightness);
    colorWidget.value = value;
    updatingPicker = true;
    try {
      colorWidget.callback?.(value);
    } finally {
      updatingPicker = false;
    }
    paint();
    node.setDirtyCanvas?.(true, true);
  };
  const updatePoint = (event) => {
    const bounds = palette.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    saturation = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
    brightness = 1 - Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height));
    applyColor();
  };
  palette.addEventListener("pointerdown", (event) => {
    event.stopPropagation();
    palette.setPointerCapture(event.pointerId);
    updatePoint(event);
  });
  palette.addEventListener("pointermove", (event) => {
    if (palette.hasPointerCapture(event.pointerId)) updatePoint(event);
  });
  palette.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") saturation = Math.max(0, saturation - 0.01);
    else if (event.key === "ArrowRight") saturation = Math.min(1, saturation + 0.01);
    else if (event.key === "ArrowUp") brightness = Math.min(1, brightness + 0.01);
    else if (event.key === "ArrowDown") brightness = Math.max(0, brightness - 0.01);
    else return;
    event.preventDefault();
    event.stopPropagation();
    applyColor();
  });
  hueSlider.addEventListener("pointerdown", (event) => event.stopPropagation());
  hueSlider.addEventListener("input", () => {
    hue = Number(hueSlider.value);
    applyColor();
  });
  const addSwatch = (hex, position) => {
    const button = document.createElement("button");
    button.type = "button";
    button.title = hex;
    button.setAttribute("aria-label", `选择颜色 ${hex}`);
    button.style.cssText = `width:18px;height:18px;padding:0;border:1px solid #ffffff44;border-radius:3px;background:${hex};cursor:pointer;`;
    const fraction = position / 359;
    button.style.position = "absolute";
    button.style.left = `calc(7px + ${fraction * 100}% - ${fraction * 14}px)`;
    button.style.transform = "translateX(-50%)";
    button.addEventListener("pointerdown", (event) => event.stopPropagation());
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const hsv = hexToHsv(hex, hue);
      hue = hsv.hue;
      saturation = hsv.saturation;
      brightness = hsv.value;
      applyColor();
    });
    swatches.appendChild(button);
  };
  for (let position = 0; position < 360; position += 30) {
    addSwatch(hsvToHex(position, 0.82, 1), position);
  }
  addSwatch(hsvToHex(359, 0.82, 1), 359);
  const originalCallback = colorWidget.callback;
  colorWidget.callback = function (...args) {
    const result = originalCallback?.apply(this, args);
    if (!updatingPicker) syncPicker();
    return result;
  };

  node.addDOMWidget("选择颜色", "kk-color-picker", root, {
    serialize: false,
    getMinHeight: () => 176,
    getMaxHeight: () => 176,
  });
  node.__kkColorPicker = { syncPicker };
  syncPicker();
  const size = node.computeSize?.();
  if (size && node.setSize) node.setSize([Math.max(node.size?.[0] || 0, size[0]), Math.max(node.size?.[1] || 0, size[1])]);
}

app.registerExtension({
  name: "kktools.color-picker",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;
    const configured = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const result = configured?.apply(this, args);
      setupPicker(this);
      this.__kkColorPicker?.syncPicker();
      return result;
    };
  },
  nodeCreated(node) {
    if ((node?.comfyClass || node?.type || node?.constructor?.comfyClass) === NODE_NAME) setupPicker(node);
  },
  loadedGraphNode(node) {
    if ((node?.comfyClass || node?.type || node?.constructor?.comfyClass) === NODE_NAME) {
      setupPicker(node);
      node.__kkColorPicker?.syncPicker();
    }
  },
});
