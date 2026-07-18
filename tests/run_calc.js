const fs = require('fs');
const path = require('path');

const appJsPath = path.join(__dirname, '..', 'frontend', 'app.js');
const inputJson = fs.readFileSync(0, 'utf8');
const inputData = JSON.parse(inputJson);

// Helper to create a robust mock DOM element
const createMockElement = () => {
    const el = {
        addEventListener: () => {},
        classList: {
            add: () => {},
            remove: () => {},
            contains: () => false,
            toggle: () => {}
        },
        style: {},
        closest: () => el,
        appendChild: () => el,
        setAttribute: () => {},
        getAttribute: () => null,
        removeAttribute: () => {},
        querySelectorAll: () => [],
        querySelector: () => el,
        focus: () => {},
        blur: () => {}
    };
    el.textContent = "";
    el.value = "";
    el.className = "";
    el.innerHTML = "";
    return el;
};

// Mock document
global.document = {
    addEventListener: (event, callback) => {
        if (event === 'DOMContentLoaded') {
            global.domLoadedCallback = callback;
        }
    },
    createElement: (tag) => createMockElement(),
    head: createMockElement(),
    getElementById: (id) => {
        if (!global[id]) {
            global[id] = createMockElement();
        }
        return global[id];
    },
    querySelectorAll: (sel) => [],
    querySelector: (sel) => createMockElement()
};

// Create a Proxy for window/global to handle both window properties and global namespace synchronization
const windowProxy = new Proxy(global, {
    get: (target, prop) => {
        if (prop === 'addEventListener') {
            return () => {};
        }
        if (prop === 'document') {
            return global.document;
        }
        if (prop === 'window') {
            return windowProxy;
        }
        if (prop === 'fetch') {
            return () => Promise.resolve({
                ok: true,
                status: 200,
                json: () => Promise.resolve({ vector_db: "online" })
            });
        }
        if (prop in target) {
            return target[prop];
        }
        if (typeof prop === 'string') {
            // Cache it on target so subsequent reads get the same mock element
            target[prop] = createMockElement();
            return target[prop];
        }
        return undefined;
    },
    set: (target, prop, value) => {
        target[prop] = value;
        return true;
    }
});

global.window = windowProxy;
global.onerror = null;

// Evaluate the app.js code
const code = fs.readFileSync(appJsPath, 'utf8');
eval(code);

if (global.domLoadedCallback) {
    global.domLoadedCallback();
}

if (!global.calculateCompensationLocally) {
    console.error("calculateCompensationLocally not found on global/window object!");
    process.exit(1);
}

const result = global.calculateCompensationLocally(inputData);
console.log(JSON.stringify(result));
