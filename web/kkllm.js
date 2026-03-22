import { app } from "../../scripts/app.js";

const PROVIDER_MODELS = {
    deepseek: [
        "deepseek-chat",
        "deepseek-reasoner",
        "custom",
    ],
    openai: [
        "gpt-5.4",
        "gpt-5.4-pro",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-5.1",
        "gpt-5",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4o",
        "gpt-4o-mini",
        "o3",
        "o4-mini",
        "o3-mini",
        "custom",
    ],
    gemini: [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "custom",
    ],
    doubao: [
        "doubao-seed-1-6-251015",
        "doubao-seed-1-6-250615",
        "doubao-seed-1-6-thinking-250715",
        "doubao-seed-1-6-flash-250715",
        "doubao-1-5-thinking-pro",
        "doubao-1-5-thinking-vision-pro",
        "doubao-1-5-pro-32k-250115",
        "doubao-1-5-lite-32k-250115",
        "custom",
    ],
};

function getWidget(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}

function updateModelOptions(node, providerValue) {
    const modelWidget = getWidget(node, "model");
    if (!modelWidget) {
        return;
    }

    const currentValue = modelWidget.value;
    const values = [...(PROVIDER_MODELS[providerValue] || PROVIDER_MODELS.deepseek)];

    if (currentValue && !values.includes(currentValue) && currentValue !== "custom") {
        values.unshift(currentValue);
    }

    modelWidget.options.values = values;
    if (!values.includes(modelWidget.value)) {
        modelWidget.value = values[0];
    }

    node.setDirtyCanvas(true, true);
}

function bindProviderModelLink(node) {
    if (node.__kkllmModelLinked) {
        return;
    }

    const providerWidget = getWidget(node, "provider");
    const modelWidget = getWidget(node, "model");
    if (!providerWidget || !modelWidget) {
        return;
    }

    const originalProviderCallback = providerWidget.callback;
    providerWidget.callback = (...args) => {
        if (originalProviderCallback) {
            originalProviderCallback.apply(providerWidget, args);
        }
        updateModelOptions(node, providerWidget.value);
    };

    updateModelOptions(node, providerWidget.value);
    node.__kkllmModelLinked = true;
}

app.registerExtension({
    name: "kktools.kkllm.models",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "kkLLM") {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            bindProviderModelLink(this);
            return result;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            bindProviderModelLink(this);
            const providerWidget = getWidget(this, "provider");
            if (providerWidget) {
                updateModelOptions(this, providerWidget.value);
            }
            return result;
        };
    },
});
