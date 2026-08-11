// frontend/general_chatbot.js
// ==========================================================================
// GENERAL CHATBOT (TEST FEATURE) — DeepSeek-powered document Q&A widget
// --------------------------------------------------------------------------
// Fully self-contained. To remove this feature later:
//   1. Delete this file.
//   2. Remove the <script src="general_chatbot.js"></script> tag from index.html.
//   3. Remove the HTML block (id="general-chatbot-trigger" + id="general-chatbot-panel").
//   4. Remove the CSS block marked "GENERAL CHATBOT (TEST FEATURE)" from style.css.
//   5. Delete backend/general_chatbot.py and its 2 lines in backend/main.py.
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
    const trigger = document.getElementById("general-chatbot-trigger");
    const panel = document.getElementById("general-chatbot-panel");
    const closeBtn = document.getElementById("gcb-close-btn");

    const fileInput = document.getElementById("gcb-file-input");
    const uploadBtn = document.getElementById("gcb-upload-btn");
    const uploadZone = document.getElementById("gcb-upload-zone");
    const fileInfo = document.getElementById("gcb-file-info");
    const fileNameEl = document.getElementById("gcb-file-name");
    const removeFileBtn = document.getElementById("gcb-remove-file-btn");

    const messagesEl = document.getElementById("gcb-messages");
    const inputEl = document.getElementById("gcb-input");
    const sendBtn = document.getElementById("gcb-send-btn");

    if (!trigger || !panel) return; // markup not present on this page

    let gcbSessionId = null;
    let gcbFilename = null;
    let gcbHistory = [];

    // -------------------- Panel open/close --------------------
    trigger.addEventListener("click", () => {
        panel.classList.toggle("open");
        trigger.classList.toggle("active");
    });

    if (closeBtn) {
        closeBtn.addEventListener("click", () => {
            panel.classList.remove("open");
            trigger.classList.remove("active");
        });
    }

    // -------------------- Upload flow --------------------
    if (uploadZone) {
        uploadZone.addEventListener("click", () => fileInput && fileInput.click());
    }
    if (uploadBtn) {
        uploadBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            fileInput && fileInput.click();
        });
    }

    if (fileInput) {
        fileInput.addEventListener("change", async () => {
            const file = fileInput.files[0];
            if (!file) return;
            await uploadDocument(file);
            fileInput.value = "";
        });
    }

    if (uploadZone) {
        ["dragover", "dragenter"].forEach(evt => {
            uploadZone.addEventListener(evt, (e) => {
                e.preventDefault();
                uploadZone.classList.add("gcb-drag-over");
            });
        });
        ["dragleave", "drop"].forEach(evt => {
            uploadZone.addEventListener(evt, (e) => {
                e.preventDefault();
                uploadZone.classList.remove("gcb-drag-over");
            });
        });
        uploadZone.addEventListener("drop", async (e) => {
            const file = e.dataTransfer.files[0];
            if (file) await uploadDocument(file);
        });
    }

    async function uploadDocument(file) {
        addSystemMessage(`Uploading "${file.name}"...`);
        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch("/api/general-chat/upload", {
                method: "POST",
                body: formData
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Upload failed");

            gcbSessionId = data.session_id;
            gcbFilename = data.filename;
            gcbHistory = [];
            messagesEl.innerHTML = "";

            if (fileInfo) fileInfo.style.display = "flex";
            if (fileNameEl) fileNameEl.textContent = data.filename;
            if (uploadZone) uploadZone.style.display = "none";

            addBotMessage(`Got it — I've read through **${data.filename}** (${data.char_count.toLocaleString()} characters). Ask me anything about it.`);
            if (inputEl) { inputEl.disabled = false; inputEl.focus(); }
            if (sendBtn) sendBtn.disabled = false;
        } catch (err) {
            console.error("General Chatbot upload error:", err);
            addBotMessage(`Sorry, I couldn't read that file: ${err.message}`);
        }
    }

    if (removeFileBtn) {
        removeFileBtn.addEventListener("click", async () => {
            if (gcbSessionId) {
                try {
                    await fetch("/api/general-chat/clear", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ session_id: gcbSessionId })
                    });
                } catch (e) { /* non-fatal */ }
            }
            gcbSessionId = null;
            gcbFilename = null;
            gcbHistory = [];
            messagesEl.innerHTML = "";
            if (fileInfo) fileInfo.style.display = "none";
            if (uploadZone) uploadZone.style.display = "flex";
            if (inputEl) inputEl.disabled = true;
            if (sendBtn) sendBtn.disabled = true;
            addSystemMessage("Document removed. Upload a new one to keep chatting.");
        });
    }

    // -------------------- Chat flow --------------------
    if (sendBtn) sendBtn.addEventListener("click", handleSend);
    if (inputEl) {
        inputEl.addEventListener("keypress", (e) => {
            if (e.key === "Enter") handleSend();
        });
    }

    async function handleSend() {
        const question = inputEl.value.trim();
        if (!question) return;
        if (!gcbSessionId) {
            addBotMessage("Please upload a document first, then ask your question.");
            return;
        }

        addUserMessage(question);
        inputEl.value = "";

        const loadingId = addBotMessage(`<i class="fa-solid fa-spinner fa-spin"></i> Thinking...`, true);

        try {
            const response = await fetch("/api/general-chat/ask", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: gcbSessionId,
                    question: question,
                    history: gcbHistory.slice(-12)
                })
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.detail || "General Chatbot API error");
            }

            document.getElementById(loadingId)?.remove();

            const botId = addBotMessage("", false);
            const botTextEl = document.querySelector(`#${botId} .gcb-text`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let accumulated = "";
            let buffer = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop();

                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const parsed = JSON.parse(line);
                        const token = parsed.message?.content || "";
                        accumulated += token;
                        if (botTextEl) botTextEl.innerHTML = formatText(accumulated);
                        messagesEl.scrollTop = messagesEl.scrollHeight;
                    } catch (e) { /* ignore partial line */ }
                }
            }
            if (buffer.trim()) {
                try {
                    const parsed = JSON.parse(buffer);
                    const token = parsed.message?.content || "";
                    accumulated += token;
                    if (botTextEl) botTextEl.innerHTML = formatText(accumulated);
                } catch (e) { /* ignore */ }
            }

            gcbHistory.push({ role: "user", content: question });
            gcbHistory.push({ role: "assistant", content: accumulated });

        } catch (err) {
            console.error("General Chatbot ask error:", err);
            document.getElementById(loadingId)?.remove();
            addBotMessage(`Sorry, something went wrong: ${err.message}`);
        }
    }

    function formatText(text) {
        return text
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.*?)\*/g, "<em>$1</em>")
            .replace(/\n/g, "<br>");
    }

    function addUserMessage(text) {
        const id = `gcb_msg_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        const el = document.createElement("div");
        el.id = id;
        el.className = "gcb-bubble gcb-user";
        el.innerHTML = `
            <div class="gcb-avatar"><i class="fa-solid fa-user"></i></div>
            <div class="gcb-text">${escapeHtml(text)}</div>
        `;
        messagesEl.appendChild(el);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return id;
    }

    function addBotMessage(html, isLoader = false) {
        const id = `gcb_msg_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        const el = document.createElement("div");
        el.id = id;
        el.className = "gcb-bubble gcb-bot";
        el.innerHTML = `
            <div class="gcb-avatar"><i class="fa-solid fa-comment-dots"></i></div>
            <div class="gcb-text">${isLoader ? html : formatText(html)}</div>
        `;
        messagesEl.appendChild(el);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return id;
    }

    function addSystemMessage(text) {
        const el = document.createElement("div");
        el.className = "gcb-system-note";
        el.textContent = text;
        messagesEl.appendChild(el);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
});
