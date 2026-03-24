import { app } from "../../scripts/app.js";

const NODE_PROVIDER_MODELS = {
    kkLLM: {
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
    },
    StoryboardScriptLLM: {
        deepseek: [
            "deepseek-chat",
            "deepseek-reasoner",
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
        ],
        gemini: [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
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
        ],
    },
};

const SUPPORTED_NODES = new Set(Object.keys(NODE_PROVIDER_MODELS));

function getWidget(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}

function getProviderModels(node) {
    const nodeName = node.__kktoolsProviderModelNodeName || node.comfyClass || "kkLLM";
    return NODE_PROVIDER_MODELS[nodeName] || NODE_PROVIDER_MODELS.kkLLM;
}

function updateModelOptions(node, providerValue, options = {}) {
    const modelWidget = getWidget(node, "model");
    if (!modelWidget) {
        return;
    }

    const { preserveCurrent = false, forceDefault = false } = options;
    const providerModels = getProviderModels(node);
    const currentValue = modelWidget.value;
    const defaultValues = providerModels.deepseek || [];
    const values = [...(providerModels[providerValue] || defaultValues)];

    if (preserveCurrent && currentValue && !values.includes(currentValue) && currentValue !== "custom") {
        values.unshift(currentValue);
    }

    modelWidget.options.values = [...values];
    if (forceDefault && values.length > 0) {
        modelWidget.value = values[0];
    } else if (!values.includes(modelWidget.value)) {
        modelWidget.value = values[0];
    }

    node.__kktoolsLastProviderValue = providerValue;
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
        const nextProviderValue = providerWidget.value;
        const providerChanged = node.__kktoolsLastProviderValue !== nextProviderValue;
        updateModelOptions(node, nextProviderValue, { forceDefault: providerChanged });
    };

    updateModelOptions(node, providerWidget.value, { preserveCurrent: true });
    node.__kkllmModelLinked = true;
}

app.registerExtension({
    name: "kktools.kkllm.models",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!SUPPORTED_NODES.has(nodeData.name)) {
            return;
        }

        nodeType.prototype.__kktoolsProviderModelNodeName = nodeData.name;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            this.__kktoolsProviderModelNodeName = nodeData.name;
            bindProviderModelLink(this);
            return result;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            this.__kktoolsProviderModelNodeName = nodeData.name;
            bindProviderModelLink(this);
            const providerWidget = getWidget(this, "provider");
            if (providerWidget) {
                updateModelOptions(this, providerWidget.value, { preserveCurrent: true });
            }
            return result;
        };
    },
});
