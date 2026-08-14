
/* ==========================================================================
   COMPENSATION CALCULATOR WORKSTATION - FRONTEND DASHBOARD ENGINE
   ========================================================================== */

// Global Error Handler to shield against silent crashes (Task 19)
window.onerror = function (msg, src, line, col, err) {
    console.error("GLOBAL ERROR DETECTED:", msg, "at", src, "line:", line, err);
};

// crypto.randomUUID() only exists in secure contexts (HTTPS or localhost).
// This app may be accessed over plain HTTP via a LAN IP, where it's undefined.
// crypto.getRandomValues() has no such restriction, so build the UUID from that.
function generateCaseSessionId() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
        try {
            return crypto.randomUUID();
        } catch (e) {
            // fall through to manual generation
        }
    }
    if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
        const bytes = crypto.getRandomValues(new Uint8Array(16));
        bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
        bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant
        const hex = [...bytes].map(b => b.toString(16).padStart(2, "0")).join("");
        return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
    }
    // Last-resort fallback (not cryptographically strong, but fine for a client-side session id)
    return "case-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

document.addEventListener("DOMContentLoaded", () => {

    // --- STATE VARIABLES ---
    let activeTab = "calculator";
    let fileQueue = []; // Local file tracker
    let uploadedFileObjects = {}; // Maps filename -> File object for local blob previews
    let isPolling = false;
    let currentCalculationAmount = 0;
    let currentCalculationBreakdown = {};
    let currentOcrRawText = []; // Recover raw text from the last successful single OCR
    window.autofillReadyPromise = Promise.resolve();
    let lastAiRecoverySignature = null;
    let lastAiRecoveryResult = null;
    let currentCaseSessionId = null;

    function ensureCaseSessionId() {
        if (!currentCaseSessionId) {
            currentCaseSessionId = generateCaseSessionId();
        }
        return currentCaseSessionId;
    }

    // Generate session ID up-front on page load
    ensureCaseSessionId();

    // Global Cache for Extracted Field Population (Part 5)
    let lastExtractedFields = {};
    let lastExtractedConfidences = {};
    let lastExtractedReasons = {};

    // --- OCR LIVE TIMER STATE & HELPERS ---
    let ocrTimerInterval = null;
    let ocrSecondsElapsed = 0;

    function formatTimeMMSS(totalSeconds) {
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }

    function startOcrTimer() {
        if (ocrTimerInterval) {
            clearInterval(ocrTimerInterval);
        }
        ocrSecondsElapsed = 0;

        const timerContainer = document.getElementById("ocr-timer-container");
        const statusIcon = document.getElementById("ocr-timer-status-icon");
        const statusText = document.getElementById("ocr-timer-status-text");
        const elapsedText = document.getElementById("ocr-timer-elapsed");

        const headerTimerContainer = document.getElementById("header-ocr-timer-badge");
        const headerElapsedText = document.getElementById("header-ocr-timer-elapsed");

        if (timerContainer) {
            timerContainer.classList.remove("hidden-section");
            timerContainer.style.display = "flex";
        }
        if (statusIcon) {
            statusIcon.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-glow" style="color: var(--color-primary);"></i>`;
        }
        if (statusText) {
            statusText.textContent = "Processing PDF...";
            statusText.style.color = "var(--text-primary)";
        }
        if (elapsedText) {
            elapsedText.textContent = "00:00";
            elapsedText.style.color = "var(--color-primary)";
        }

        if (headerTimerContainer) {
            headerTimerContainer.classList.remove("hidden-section");
            headerTimerContainer.style.display = "inline-flex";
            headerTimerContainer.style.color = "var(--color-primary)";
            headerTimerContainer.style.borderColor = "rgba(11, 58, 114, 0.25)";
            headerTimerContainer.style.background = "rgba(11, 58, 114, 0.06)";
        }
        if (headerElapsedText) {
            headerElapsedText.textContent = "00:00";
        }

        ocrTimerInterval = setInterval(() => {
            ocrSecondsElapsed++;
            const formattedTime = formatTimeMMSS(ocrSecondsElapsed);
            if (elapsedText) {
                elapsedText.textContent = formattedTime;
            }
            if (headerElapsedText) {
                headerElapsedText.textContent = formattedTime;
            }
            const loaderTimer = document.getElementById("ocr-loader-timer");
            if (loaderTimer) {
                loaderTimer.textContent = formattedTime;
            }
        }, 1000);
    }

    function stopOcrTimerSuccess() {
        if (ocrTimerInterval) {
            clearInterval(ocrTimerInterval);
            ocrTimerInterval = null;
        }
        const statusIcon = document.getElementById("ocr-timer-status-icon");
        const statusText = document.getElementById("ocr-timer-status-text");
        const elapsedText = document.getElementById("ocr-timer-elapsed");

        const headerTimerContainer = document.getElementById("header-ocr-timer-badge");
        const headerElapsedText = document.getElementById("header-ocr-timer-elapsed");

        if (statusIcon) {
            statusIcon.innerHTML = `<i class="fa-solid fa-circle-check" style="color: var(--color-success);"></i>`;
        }
        if (statusText) {
            statusText.textContent = "OCR complete";
            statusText.style.color = "var(--color-success)";
        }
        if (elapsedText) {
            elapsedText.textContent = `Total time: ${formatTimeMMSS(ocrSecondsElapsed)}`;
            elapsedText.style.color = "var(--color-success)";
        }

        if (headerElapsedText && headerTimerContainer) {
            headerElapsedText.textContent = `Complete: ${formatTimeMMSS(ocrSecondsElapsed)}`;
            headerTimerContainer.style.color = "var(--color-success)";
            headerTimerContainer.style.borderColor = "rgba(22, 163, 74, 0.3)";
            headerTimerContainer.style.background = "rgba(22, 163, 74, 0.08)";
        }
    }

    function stopOcrTimerFailure() {
        if (ocrTimerInterval) {
            clearInterval(ocrTimerInterval);
            ocrTimerInterval = null;
        }
        const statusIcon = document.getElementById("ocr-timer-status-icon");
        const statusText = document.getElementById("ocr-timer-status-text");
        const elapsedText = document.getElementById("ocr-timer-elapsed");

        const headerTimerContainer = document.getElementById("header-ocr-timer-badge");
        const headerElapsedText = document.getElementById("header-ocr-timer-elapsed");

        if (statusIcon) {
            statusIcon.innerHTML = `<i class="fa-solid fa-circle-xmark" style="color: var(--color-danger);"></i>`;
        }
        if (statusText) {
            statusText.textContent = "OCR failed";
            statusText.style.color = "var(--color-danger)";
        }
        if (elapsedText) {
            elapsedText.textContent = `Failed after ${formatTimeMMSS(ocrSecondsElapsed)}`;
            elapsedText.style.color = "var(--color-danger)";
        }

        if (headerElapsedText && headerTimerContainer) {
            headerElapsedText.textContent = `Failed: ${formatTimeMMSS(ocrSecondsElapsed)}`;
            headerTimerContainer.style.color = "var(--color-danger)";
            headerTimerContainer.style.borderColor = "rgba(220, 38, 38, 0.3)";
            headerTimerContainer.style.background = "rgba(220, 38, 38, 0.08)";
        }
    }

    // Programmatically Inject Suggestion Badge CSS Styles
    const styleEl = document.createElement("style");
    styleEl.innerHTML = `
        .suggested-badge {
            display: inline-flex !important;
            align-items: center !important;
            gap: 6px !important;
            margin-top: 6px !important;
            background: #fef3c7 !important; /* warm amber background for high contrast */
            color: #b45309 !important; /* dark amber text for readable AAA-level contrast */
            border: 1px solid #fde68a !important;
            padding: 5px 10px !important;
            border-radius: 6px !important;
            font-size: 0.75rem !important;
            font-weight: 600 !important;
            cursor: pointer !important;
            transition: all 0.2s ease !important;
            user-select: none !important;
            width: fit-content !important;
            box-shadow: 0 1px 2px rgba(180, 83, 9, 0.08) !important;
        }
        .suggested-badge:hover {
            background: #fcd34d !important;
            border-color: #fbbf24 !important;
            color: #78350f !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 2px 4px rgba(180, 83, 9, 0.15) !important;
        }
        .low-confidence-input {
            border-color: #fbbf24 !important;
            box-shadow: 0 0 0 2px rgba(251, 191, 36, 0.15) !important;
        }
    `;
    document.head.appendChild(styleEl);

    // Dynamically Inject Audit Log Card (Part 7)
    const ocrQualityTab = document.getElementById("pane-tab-ocr-quality-content");
    if (ocrQualityTab) {
        let auditCard = document.getElementById("extraction-audit-log-card");
        if (!auditCard) {
            auditCard = document.createElement("div");
            auditCard.id = "extraction-audit-log-card";
            auditCard.className = "card";
            auditCard.style.marginTop = "20px";
            auditCard.innerHTML = `
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                    <h3><i class="fa-solid fa-clipboard-list text-glow" style="color: #f59e0b;"></i> Case Type &amp; Extraction Audit Log</h3>
                    <span class="badge tech-badge" id="audit-log-badge" style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3);">Audit Log</span>
                </div>
                <div class="card-body" style="padding-top: 12px; display: flex; flex-direction: column; gap: 15px;">
                    <div class="metrics-grid" style="grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));">
                        <div class="metric-item">
                            <span class="label">User Case Type</span>
                            <span class="value" id="audit-val-user-case" style="color: #60a5fa; font-weight: 600;">—</span>
                        </div>
                        <div class="metric-item">
                            <span class="label">LLM Case Type</span>
                            <span class="value" id="audit-val-llm-case" style="color: #c084fc; font-weight: 600;">—</span>
                        </div>
                        <div class="metric-item">
                            <span class="label">OCR Evidence</span>
                            <span class="value" id="audit-val-ocr-evidence" style="color: #34d399; font-weight: 600;">—</span>
                        </div>
                        <div class="metric-item">
                            <span class="label">Avg Confidence</span>
                            <span class="value" id="audit-val-confidence" style="color: #f59e0b; font-weight: 600;">—</span>
                        </div>
                        <div class="metric-item">
                            <span class="label">Overwrite Blocked</span>
                            <span class="value" id="audit-val-overwrite-blocked" style="font-weight: 700;">—</span>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 5px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 10px;">
                        <span style="font-size: 0.8rem; color: #94a3b8;"><i class="fa-solid fa-sliders"></i> Flag Fields Below:</span>
                        <select id="autofill-threshold-select" style="background: var(--bg-panel); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 2px 6px; font-size: 0.8rem;">
                            <option value="0.50">50%</option>
                            <option value="0.60">60%</option>
                            <option value="0.70">70%</option>
                            <option value="0.75" selected>75%</option>
                            <option value="0.80">80%</option>
                            <option value="0.85">85%</option>
                            <option value="0.90">90%</option>
                            <option value="0.95">95%</option>
                        </select>
                    </div>
                    <div style="background: rgba(10, 15, 30, 0.6); border: 1px solid var(--border-glass); border-radius: var(--radius-sm); padding: 12px; font-family: monospace; font-size: 0.8rem; max-height: 150px; overflow-y: auto; line-height: 1.4; color: #94a3b8;" id="audit-log-terminal">
                        <span style="color: #64748b;">[SYSTEM] Ready. Awaiting document upload or LLM extraction...</span>
                    </div>
                </div>
            `;
            const rawCard = document.getElementById("ocr-raw-text-card");
            if (rawCard) {
                ocrQualityTab.insertBefore(auditCard, rawCard);
            } else {
                ocrQualityTab.appendChild(auditCard);
            }

            const thresholdSelect = document.getElementById("autofill-threshold-select");
            if (thresholdSelect) {
                const storedVal = localStorage.getItem("autofill_confidence_threshold");
                if (storedVal) {
                    thresholdSelect.value = storedVal;
                }
                thresholdSelect.addEventListener("change", (e) => {
                    localStorage.setItem("autofill_confidence_threshold", e.target.value);
                    populateFieldsForActiveCaseType();
                    showToast(`Autofill visual warning threshold updated to ${Math.round(parseFloat(e.target.value) * 100)}%`, "info");
                });
            }
        }
    }



    // --- DOM REFERENCES ---
    const navItems = document.querySelectorAll(".nav-item");
    const viewports = document.querySelectorAll(".tab-viewport");
    const tabTitleText = document.getElementById("tab-title-text");
    const dbStatusText = document.getElementById("db-status-text");
    const statusDot = document.querySelector(".status-dot");
    const serverStatus = document.getElementById("server-status");
    const pulseIndicator = document.querySelector(".pulse-indicator");

    // TAB 1: CALCULATOR WORKSPACE
    const caseTypeSelect = document.getElementById("case-type");
    const sharedFields = document.getElementById("shared-fields");
    const deathFields = document.getElementById("death-fields");
    const injuryFields = document.getElementById("injury-fields");
    const formActionsBar = document.getElementById("form-actions-bar");
    const compensationForm = document.getElementById("compensation-form");

    // Single Case PDF Upload & Preview
    const singleUploadSection = document.getElementById("single-upload-section");
    const singleDropZone = document.getElementById("single-drop-zone");
    const singleFileInput = document.getElementById("single-file-input");
    const singlePreviewCard = document.getElementById("single-preview-card");
    const singlePreviewContainer = document.getElementById("single-preview-container");
    const singlePreviewFilename = document.getElementById("single-preview-filename");
    const downloadWordBtn = document.getElementById("download-word-btn");

    // Age & Dates
    const dobInput = document.getElementById("date-of-birth");
    const doaInput = document.getElementById("date-of-accident");
    const ageInput = document.getElementById("age");

    // Live previews
    const liveMetricsCard = document.getElementById("live-metrics-card");
    const liveAge = document.getElementById("live-age");
    const liveMultiplier = document.getElementById("live-multiplier");
    const liveProspects = document.getElementById("live-prospects");
    const liveProspectsBar = document.getElementById("live-prospects-bar");
    const liveProspectsItem = document.getElementById("live-prospects-item");
    const liveDeductions = document.getElementById("live-deductions");
    const liveDeductionsBar = document.getElementById("live-deductions-bar");
    const liveDeductionsItem = document.getElementById("live-deductions-item");

    // Extra elements
    const dependentsInput = document.getElementById("dependents");
    const maritalStatusSelect = document.getElementById("marital-status");
    const futureTypeSelect = document.getElementById("future-type");
    const monthlyIncomeInput = document.getElementById("monthly-income");

    // Precedents benchmarking
    const evaluatorCard = document.getElementById("evaluator-card");
    const triggerEvalBtn = document.getElementById("trigger-eval-btn");
    const evaluatorCardBody = document.getElementById("evaluator-card-body");

    // TAB 2: PDF LIBRARY
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const batchFileList = document.getElementById("batch-file-list");
    const queueBadge = document.getElementById("queue-badge");
    const queueCountLabel = document.getElementById("queue-count-label");
    const previewContainer = document.getElementById("preview-container");
    const previewFilenameBadge = document.getElementById("preview-filename-badge");

    // TAB 3: AI LEGAL CHAT
    const chatInput = document.getElementById("chat-input");
    const chatSendBtn = document.getElementById("chat-send-btn");
    const chatMessages = document.getElementById("chat-messages");
    const chatCaseFilter = document.getElementById("chat-case-filter");
    const clearPrecedentChatBtn = document.getElementById("clear-precedent-chat-btn");
    let precedentChatHistory = [];

    // MODAL DASHBOARD
    const resultsModal = document.getElementById("results-modal");
    const modalBodyContent = document.getElementById("modal-body-content");
    const closeModalBtn = document.getElementById("close-modal-btn");
    const dismissModalBtn = document.getElementById("dismiss-modal-btn");
    const printBtn = document.getElementById("print-btn");

    // Glassmorphic Premium Toast Notification System
    function showToast(message, type = "info") {
        let container = document.getElementById("toast-container");
        if (!container) {
            container = document.createElement("div");
            container.id = "toast-container";
            container.style.cssText = `
                position: fixed;
                bottom: 24px;
                right: 24px;
                display: flex;
                flex-direction: column;
                gap: 12px;
                z-index: 9999;
                max-width: 360px;
                pointer-events: none;
            `;
            document.body.appendChild(container);
        }

        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;

        let icon = "fa-info-circle";
        let color = "var(--color-primary, #3b82f6)";
        if (type === "success") {
            icon = "fa-circle-check";
            color = "#10b981";
        } else if (type === "error") {
            icon = "fa-triangle-exclamation";
            color = "#ef4444";
        } else if (type === "warning") {
            icon = "fa-circle-exclamation";
            color = "#f59e0b";
        }

        toast.style.cssText = `
            background: rgba(30, 41, 59, 0.85);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-left: 4px solid ${color};
            color: #f1f5f9;
            padding: 14px 18px;
            border-radius: 8px;
            font-family: 'Inter', sans-serif;
            font-size: 0.875rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -4px rgba(0, 0, 0, 0.3);
            display: flex;
            align-items: center;
            gap: 12px;
            transform: translateY(20px);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            pointer-events: auto;
        `;

        toast.innerHTML = `
            <i class="fa-solid ${icon}" style="color: ${color}; font-size: 1.125rem;"></i>
            <span style="flex-grow: 1; line-height: 1.4;">${message}</span>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.transform = "translateY(0)";
            toast.style.opacity = "1";
        }, 50);

        setTimeout(() => {
            toast.style.transform = "translateY(-20px)";
            toast.style.opacity = "0";
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 4000);
    }

    // ==========================================================================
    // SIDEBAR TAB CONTROLLERS
    // ==========================================================================
    navItems.forEach(item => {
        item.addEventListener("click", () => {
            const target = item.getAttribute("data-tab");
            switchTab(target);
        });
    });

    function switchTab(tabName) {
        activeTab = tabName;

        // Active indicator on navigation
        navItems.forEach(item => {
            if (item.getAttribute("data-tab") === tabName) {
                item.classList.add("active");
            } else {
                item.classList.remove("active");
            }
        });

        // Toggle viewport display
        viewports.forEach(vp => {
            if (vp.id === `tab-${tabName}`) {
                vp.classList.add("active-viewport");
            } else {
                vp.classList.remove("active-viewport");
            }
        });

        // Update Title text
        const titleMap = {
            calculator: "High Court Compensation Calculator",
            library: "Centralized PDF Library & Qdrant Queue",
            chat: "AI Precedent Assistant & Semantic Search",
            qdrant: "Qdrant Vector Database Explorer Dashboard"
        };
        tabTitleText.textContent = titleMap[tabName] || "Compensation Calculator Workstation";

        // Trigger dashboard reload when viewing Qdrant DB Explorer
        if (tabName === "qdrant") {
            loadQdrantDashboard();
        }
    }

    // ==========================================================================
    // EMBEDDED QDRANT OFFICIAL UI DASHBOARD EXPLORER
    // ==========================================================================
    const qdrantPointsTableBody = document.getElementById("qdrant-points-table-body");
    const qdrantCollectionName = document.getElementById("qdrant-collection-name");
    const qdrantPointsCount = document.getElementById("qdrant-points-count");
    const qdrantDistance = document.getElementById("qdrant-distance");
    const qdrantVectorSize = document.getElementById("qdrant-vector-size");
    const refreshQdrantBtn = document.getElementById("refresh-qdrant-btn");

    const payloadModal = document.getElementById("qdrant-payload-modal");
    const closePayloadModalBtn = document.getElementById("close-payload-modal-btn");
    const dismissPayloadModalBtn = document.getElementById("dismiss-payload-modal-btn");
    const payloadCodeblock = document.getElementById("qdrant-payload-codeblock");

    if (refreshQdrantBtn) {
        refreshQdrantBtn.addEventListener("click", loadQdrantDashboard);
    }

    async function loadQdrantDashboard() {
        if (!qdrantPointsTableBody) return;

        qdrantPointsTableBody.innerHTML = `
            <tr>
                <td colspan="5" style="padding: 24px; text-align: center; color: var(--text-secondary);">
                    <i class="fa-solid fa-spinner fa-spin fa-2x" style="color: var(--color-primary); margin-bottom: 8px;"></i>
                    Scrolling points and loading vectors from local Qdrant collection...
                </td>
            </tr>
        `;

        try {
            const response = await fetch("/api/qdrant/points");
            if (!response.ok) throw new Error("Failed to load Qdrant points");
            const data = await response.json();

            // Populate cards
            if (qdrantCollectionName) qdrantCollectionName.textContent = data.collection_name || "legal_documents";
            if (qdrantPointsCount) qdrantPointsCount.textContent = data.points_count !== undefined ? data.points_count : 0;
            if (qdrantDistance) qdrantDistance.textContent = data.distance || "Cosine";
            if (qdrantVectorSize) qdrantVectorSize.textContent = data.vector_size ? `${data.vector_size} dims` : "384 dims";

            if (!data.points || data.points.length === 0) {
                qdrantPointsTableBody.innerHTML = `
                    <tr>
                        <td colspan="5" style="padding: 24px; text-align: center; color: var(--text-muted);">
                            <i class="fa-solid fa-box-open" style="font-size: 1.8rem; display: block; margin-bottom: 8px;"></i>
                            No vectors currently indexed in the Qdrant database collection.<br>
                            <span style="font-size: 0.75rem; color: var(--text-muted); opacity: 0.7;">Drop a legal case PDF in the workstation to auto-OCR & populate vectors!</span>
                        </td>
                    </tr>
                `;
                return;
            }

            qdrantPointsTableBody.innerHTML = "";
            data.points.forEach(point => {
                const tr = document.createElement("tr");
                tr.style.cssText = "border-bottom: 1px solid var(--border-glass); transition: background 0.2s ease;";

                // Highlight row on hover
                tr.addEventListener("mouseenter", () => tr.style.background = "rgba(255, 255, 255, 0.01)");
                tr.addEventListener("mouseleave", () => tr.style.background = "transparent");

                const payload = point.payload || {};
                const filename = payload.filename || "unknown";
                const chunkId = payload.chunk_id !== undefined ? payload.chunk_id : 0;
                let text = payload.text || "";
                if (text.length > 75) {
                    text = text.slice(0, 72) + "...";
                }

                tr.innerHTML = `
                    <td style="padding: 12px 16px; font-family: monospace; color: var(--color-primary); font-size: 0.8rem;">${point.id}</td>
                    <td style="padding: 12px 16px; font-weight: 500;">${filename}</td>
                    <td style="padding: 12px 16px; text-align: center;"><span class="badge tech-badge" style="padding: 2px 6px;"># ${chunkId}</span></td>
                    <td style="padding: 12px 16px; color: var(--text-secondary); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">"${text}"</td>
                    <td style="padding: 12px 16px; text-align: right;">
                        <button type="button" class="btn btn-secondary btn-small view-payload-btn" data-point-id="${point.id}">
                            <i class="fa-solid fa-code"></i> Payload
                        </button>
                    </td>
                `;

                // Bind payload detail viewer
                tr.querySelector(".view-payload-btn").addEventListener("click", () => {
                    if (payloadCodeblock && payloadModal) {
                        payloadCodeblock.textContent = JSON.stringify(payload, null, 4);
                        payloadModal.classList.add("open");
                    }
                });

                qdrantPointsTableBody.appendChild(tr);
            });

        } catch (error) {
            console.error("Qdrant Explorer error:", error);
            qdrantPointsTableBody.innerHTML = `
                <tr>
                    <td colspan="5" style="padding: 24px; text-align: center; color: var(--color-danger);">
                        <i class="fa-solid fa-triangle-exclamation" style="font-size: 1.8rem; display: block; margin-bottom: 8px;"></i>
                        Failed to read points from Qdrant: ${error.message}
                    </td>
                </tr>
            `;
        }
    }

    // Modal controls for payload explorer
    if (closePayloadModalBtn) {
        closePayloadModalBtn.addEventListener("click", () => payloadModal.classList.remove("open"));
    }
    if (dismissPayloadModalBtn) {
        dismissPayloadModalBtn.addEventListener("click", () => payloadModal.classList.remove("open"));
    }
    window.addEventListener("click", (e) => {
        if (e.target === payloadModal) {
            payloadModal.classList.remove("open");
        }
    });

    // ==========================================================================
    // BACKEND HEALTH & QDRANT CONNECTOR
    // ==========================================================================
    async function checkBackendHealth() {
        try {
            const response = await fetch("/api/health");
            if (response.ok) {
                const data = await response.json();
                serverStatus.textContent = "Server Online";
                pulseIndicator.className = "pulse-indicator active";

                if (data.vector_db === "online") {
                    dbStatusText.textContent = "Qdrant Vector DB: Online";
                    statusDot.className = "status-dot online";
                } else {
                    dbStatusText.textContent = "Qdrant: Fallback Simulation";
                    statusDot.className = "status-dot";
                }
            } else {
                throw new Error("HTTP health check error");
            }
        } catch (error) {
            console.error("Health probe failed:", error);
            serverStatus.textContent = "Offline Sandbox Mode";
            pulseIndicator.className = "pulse-indicator active error";
            dbStatusText.textContent = "Qdrant: Sandbox Mode";
            statusDot.className = "status-dot";
        }
    }

    checkBackendHealth();

    // ==========================================================================
    // FORM TOGGLER & LIVE MATH ENGINE
    // ==========================================================================
    caseTypeSelect.addEventListener("change", (e) => {
        const caseType = e.target.value;

        const existingBadge = document.querySelector(`.suggested-badge[data-field="case_type"]`);
        if (existingBadge) {
            existingBadge.remove();
        }

        sharedFields.classList.remove("show");
        sharedFields.classList.add("hidden-section");

        deathFields.classList.remove("show");
        deathFields.classList.add("hidden-section");

        injuryFields.classList.remove("show");
        injuryFields.classList.add("hidden-section");

        formActionsBar.classList.remove("show-flex");
        formActionsBar.classList.add("hidden-section");

        if (liveMetricsCard) {
            liveMetricsCard.classList.remove("show");
            liveMetricsCard.classList.add("hidden-section");
        }
        if (evaluatorCard) {
            evaluatorCard.classList.remove("show");
            evaluatorCard.classList.add("hidden-section");
        }

        singleUploadSection.classList.remove("show");
        singleUploadSection.classList.remove("show-flex");
        singleUploadSection.classList.add("hidden-section");

        sharedFields.classList.remove("hidden-section");
        sharedFields.classList.add("show");

        singleUploadSection.classList.remove("hidden-section");
        singleUploadSection.classList.add("show-flex");

        if (caseType === "injury") {
            injuryFields.classList.remove("hidden-section");
            injuryFields.classList.add("show");

            if (liveDeductionsItem) liveDeductionsItem.classList.add("hidden");
            if (liveProspectsItem) liveProspectsItem.classList.add("hidden");

            const futureProspectInput = document.getElementById("future-prospect");
            if (futureProspectInput) futureProspectInput.removeAttribute("required");
        } else if (caseType === "death") {
            deathFields.classList.remove("hidden-section");
            deathFields.classList.add("show");

            if (liveDeductionsItem) liveDeductionsItem.classList.remove("hidden");
            if (liveProspectsItem) liveProspectsItem.classList.remove("hidden");

            const futureProspectInput = document.getElementById("future-prospect");
            if (futureProspectInput) futureProspectInput.setAttribute("required", "required");
        }

        const nameLabel = document.querySelector('label[for="name"]');
        if (nameLabel) {
            nameLabel.innerHTML = (caseType === "death")
                ? 'Name of Deceased <span class="req">*</span>'
                : 'Name <span class="req">*</span>';
        }

        updateDependentsVisibility();

        formActionsBar.classList.remove("hidden-section");
        formActionsBar.classList.add("show-flex");

        if (liveMetricsCard) {
            liveMetricsCard.classList.remove("hidden-section");
            liveMetricsCard.classList.add("show");
        }
        if (evaluatorCard) {
            evaluatorCard.classList.remove("hidden-section");
            evaluatorCard.classList.add("show");
        }
        // Populate fields from local cache if we already ran extraction!
        populateFieldsForActiveCaseType();

        updateLiveCalculations();


    });

    // Trigger change event dynamically to handle browser auto-restored values on page refresh
    if (caseTypeSelect && caseTypeSelect.value) {
        caseTypeSelect.dispatchEvent(new Event("change"));
    }

    // DOB & Date of Accident -> Calculated Age
    function calculateAge(dobStr, doaStr) {
        if (!dobStr || !doaStr) return null;
        const dob = new Date(dobStr);
        const doa = new Date(doaStr);
        if (isNaN(dob.getTime()) || isNaN(doa.getTime())) return null;

        let age = doa.getFullYear() - dob.getFullYear();
        const monthDiff = doa.getMonth() - dob.getMonth();
        if (monthDiff < 0 || (monthDiff === 0 && doa.getDate() < dob.getDate())) {
            age--;
        }
        return age >= 0 ? age : 0;
    }

    function getMultiplier(age) {
        if (age === null || age === undefined || age === "") return 0;
        const a = parseInt(age);
        if (a <= 15) return 15;
        if (a <= 20) return 18;
        if (a <= 25) return 18;
        if (a <= 30) return 17;
        if (a <= 35) return 16;
        if (a <= 40) return 15;
        if (a <= 45) return 14;
        if (a <= 50) return 13;
        if (a <= 55) return 11;
        if (a <= 60) return 9;
        if (a <= 65) return 7;
        return 5;
    }

    function getFutureProspectPercentage(age, futureType) {
        const fType = parseInt(futureType);
        const a = parseInt(age);
        if (isNaN(a)) return fType === 1 ? 50 : 40; // sensible default before age is entered
        if (fType === 1) { // permanent job
            if (a < 40) return 50;
            if (a <= 50) return 30;
            if (a <= 60) return 15;
            return 0;
        } else { // self-employed / fixed salary
            if (a < 40) return 40;
            if (a <= 50) return 25;
            if (a <= 60) return 10;
            return 0;
        }
    }

    function updateDependentsVisibility() {
        // Number of Dependents is required for BOTH married and bachelor
        // death cases now — the bachelor-deduction recommendation also
        // depends on how many dependents/claimants were entered.
        const caseType = caseTypeSelect ? caseTypeSelect.value : "";
        const isDeath = caseType === "death";

        const group = document.getElementById("dependents-group");
        if (group) group.style.display = isDeath ? "" : "none";

        const labelDeps = document.getElementById("label-dependents");
        if (labelDeps) {
            labelDeps.innerHTML = isDeath
                ? "Number of Dependents <span class=\"req\">*</span>"
                : "Number of Dependents";
        }

        if (dependentsInput) {
            if (isDeath) {
                dependentsInput.setAttribute("required", "required");
            } else {
                dependentsInput.removeAttribute("required");
                dependentsInput.value = "";
            }
        }
    }

    function getDeductionRatioWithReason(dependents, status) {
        // Mirrors backend/calculator.py get_deduction().
        // TODO(OCR hook): once /parse extracts a structured claimant list
        // (relation + age + earning status per claimant) for the "death"
        // case, swap this bachelor branch for the relationship-driven
        // engine (father/mother/sibling dependency presumptions) instead
        // of the raw dependents count.
        const stat = String(status || "married").trim().toLowerCase();
        const isBachelor = stat === "single" || stat === "bachelor" || stat === "b" || stat === "unmarried" || stat === "s";
        const deps = parseInt(dependents) || 0;

        if (isBachelor) {
            if (deps <= 1) {
                return {
                    ratio: 0.50,
                    label: "1/2",
                    reason: "Deceased was unmarried (bachelor). Default presumption: 50% deducted towards personal & living expenses."
                };
            } else {
                return {
                    ratio: 1 / 3,
                    label: "1/3",
                    reason: `Deceased was unmarried (bachelor) with ${deps} dependents entered — 1/3 deducted (2/3 treated as family contribution). Verify against actual evidence of a large dependent family.`
                };
            }
        } else {
            if (deps <= 3) {
                return { ratio: 1 / 3, label: "1/3", reason: `Family size ${deps + 1} (2-3 members) — 1/3 deducted per Sarla Verma.` };
            } else if (deps <= 6) {
                return { ratio: 0.25, label: "1/4", reason: `Family size ${deps + 1} (4-6 members) — 1/4 deducted per Sarla Verma.` };
            } else {
                return { ratio: 0.20, label: "1/5", reason: `Family size ${deps + 1} (7+ members) — 1/5 deducted per Sarla Verma.` };
            }
        }
    }

    // Backward-compatible ratio-only accessor used elsewhere.
    function getDeductionRatio(dependents, status) {
        return getDeductionRatioWithReason(dependents, status).ratio;
    }

    // Tracks whether the user has manually touched the deduction dropdown,
    // so auto-recalculation (on age/dependents/marital-status change)
    // doesn't silently clobber a deliberate manual override.
    let deductionManuallyOverridden = false;

    function updateLiveCalculations() {
        const age = parseInt(ageInput.value);
        const caseType = caseTypeSelect.value;

        if (caseType === "death") {
            const futureType = futureTypeSelect ? futureTypeSelect.value : 2;
            const futureProspectInput = document.getElementById("future-prospect");
            const prospects = getFutureProspectPercentage(age, futureType);
            if (futureProspectInput) {
                futureProspectInput.value = prospects;
            }
            if (liveProspects) liveProspects.textContent = `${prospects}%`;
            if (liveProspectsBar) liveProspectsBar.style.width = `${prospects}%`;
        } else {
            if (liveProspects) liveProspects.textContent = "—%";
            if (liveProspectsBar) liveProspectsBar.style.width = "0%";
        }

        if (!isNaN(age) && age >= 0) {
            if (liveAge) liveAge.textContent = `${age} years`;

            const mult = getMultiplier(age);
            if (liveMultiplier) liveMultiplier.textContent = mult;

            if (caseType === "death") {
                // Populate only helper parameters
                const deathMultInput = document.getElementById("death-multiplier");
                if (deathMultInput) deathMultInput.value = mult;

                const deps = parseInt(dependentsInput.value) || 0;
                const status = maritalStatusSelect.value || "married";
                const deductionInfo = getDeductionRatioWithReason(deps, status);
                const deductionsPercent = Math.round(deductionInfo.ratio * 100);
                if (liveDeductions) liveDeductions.textContent = `${deductionsPercent}%`;
                if (liveDeductionsBar) liveDeductionsBar.style.width = `${deductionsPercent}%`;

                const deathDeductSelect = document.getElementById("death-deduction");
                const deathDeductReason = document.getElementById("death-deduction-reason");
                if (deathDeductSelect && !deductionManuallyOverridden) {
                    deathDeductSelect.value = "auto";
                }
                if (deathDeductReason) {
                    if (deductionManuallyOverridden) {
                        deathDeductReason.className = "hint-text deduction-reason deduction-reason--override";
                        deathDeductReason.innerHTML = `<span class="deduction-reason-badge">Manual</span>Set to ${deathDeductSelect ? deathDeductSelect.value : ""} — overrides the recommended value (${deductionInfo.label}, ${deductionInfo.reason})`;
                    } else {
                        deathDeductReason.className = "hint-text deduction-reason deduction-reason--auto";
                        deathDeductReason.innerHTML = `<span class="deduction-reason-badge">Recommended</span>${deductionInfo.label} (${deductionsPercent}%) — ${deductionInfo.reason}`;
                    }
                }

                // Populate dynamic dashboard helper elements only (no monetary figures)
                if (document.getElementById("live-calc-multiplier")) {
                    document.getElementById("live-calc-multiplier").textContent = mult;
                }
                if (document.getElementById("live-calc-deduct-pct")) {
                    document.getElementById("live-calc-deduct-pct").textContent = `${deductionsPercent}%`;
                }

            } else {
                if (liveDeductions) liveDeductions.textContent = "—%";
                if (liveDeductionsBar) liveDeductionsBar.style.width = "0%";
            }
        } else {
            // Truly nothing — blank everything
            if (liveAge) liveAge.textContent = "—";
            if (liveMultiplier) liveMultiplier.textContent = "—";
            if (liveDeductions) liveDeductions.textContent = "—%";
            if (liveDeductionsBar) liveDeductionsBar.style.width = "0%";
            if (caseType === "death") {
                if (document.getElementById("live-calc-multiplier")) document.getElementById("live-calc-multiplier").textContent = "—";
                if (document.getElementById("live-calc-deduct-pct")) document.getElementById("live-calc-deduct-pct").textContent = "—";
            }
        }
    }

    const handleRecalculateDefaultProspects = () => {
        const age = parseInt(ageInput.value);
        if (!isNaN(age) && age >= 0) {
            const futureType = futureTypeSelect ? futureTypeSelect.value : 2;
            const prospects = getFutureProspectPercentage(age, futureType);
            const futureProspectInput = document.getElementById("future-prospect");
            if (futureProspectInput) futureProspectInput.value = prospects;
        }
        updateLiveCalculations();
    };

    if (futureTypeSelect) {
        futureTypeSelect.addEventListener("change", handleRecalculateDefaultProspects);
    }

    function syncAgeFromDob() {
        const computed = calculateAge(dobInput.value, doaInput.value);
        if (computed !== null) {
            ageInput.value = computed;
        }
    }

    dobInput.addEventListener("change", () => { syncAgeFromDob(); updateLiveCalculations(); });
    doaInput.addEventListener("change", () => { syncAgeFromDob(); updateLiveCalculations(); });
    maritalStatusSelect.addEventListener("change", updateLiveCalculations);
    maritalStatusSelect.addEventListener("change", updateDependentsVisibility);
    dependentsInput.addEventListener("input", updateLiveCalculations);
    monthlyIncomeInput.addEventListener("input", updateLiveCalculations);
    ageInput.addEventListener("input", handleRecalculateDefaultProspects);

    // Set dynamic update bindings for new Death Claim inputs and prospects field manual override
    setTimeout(() => {
        const consInput = document.getElementById("consortium");
        const funInput = document.getElementById("funeral-expenses");
        const estInput = document.getElementById("loss-estate");
        const futureProspectInput = document.getElementById("future-prospect");
        const deathDeductSelect = document.getElementById("death-deduction");

        if (consInput) consInput.addEventListener("input", updateLiveCalculations);
        if (funInput) funInput.addEventListener("input", updateLiveCalculations);
        if (estInput) estInput.addEventListener("input", updateLiveCalculations);
        if (futureProspectInput) futureProspectInput.addEventListener("input", updateLiveCalculations);

        if (deathDeductSelect) {
            deathDeductSelect.addEventListener("change", () => {
                deductionManuallyOverridden = deathDeductSelect.value !== "auto";
                updateLiveCalculations();
            });
        }
    }, 50);

    // Re-run the auto suggestion (and clear a stale manual override) whenever
    // the inputs that actually drive the recommendation change.
    [dependentsInput, maritalStatusSelect, ageInput].forEach((el) => {
        if (!el) return;
        el.addEventListener("change", () => {
            deductionManuallyOverridden = false;
            const sel = document.getElementById("death-deduction");
            if (sel) sel.value = "auto";
        });
    });

    // ==========================================================================
    // SINGLE PDF WORKSPACE DRAG & DROP + UPLOAD
    // ==========================================================================
    ["dragenter", "dragover"].forEach(eventName => {
        singleDropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            singleDropZone.classList.add("dragover");
        }, false);
    });

    singleDropZone.addEventListener("dragleave", (e) => {
        e.preventDefault();
        e.stopPropagation();
        singleDropZone.classList.remove("dragover");
    }, false);

    singleDropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        e.stopPropagation();
        singleDropZone.classList.remove("dragover");

        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleSinglePdfUpload(files[0]);
        }
    });

    function resetSingleUploadUI(triggerClick = false) {
        currentCaseSessionId = null;
        if (singleDropZone) {
            singleDropZone.classList.remove("compact");
        }
        if (singleFileInput) {
            singleFileInput.value = "";
            if (triggerClick) {
                singleFileInput.click();
            }
        }
        if (supportingDocsChips) {
            supportingDocsChips.innerHTML = "";
        }
        setCaseDocumentsCollapsed(false);
        setSupportingDocsCollapsed(false);
        updateCaseDocumentsBadge();
    }

    // ==========================================================================
    // CASE DOCUMENTS & SUPPORTING DOCUMENTS: collapsible sections + live badges
    // ==========================================================================
    const caseDocumentsToggle = document.getElementById("case-documents-toggle");
    const caseDocumentsBody = document.getElementById("case-documents-body");
    const caseDocumentsChevron = document.getElementById("case-documents-chevron");
    const caseDocumentsCountBadge = document.getElementById("case-documents-count-badge");

    function setCaseDocumentsCollapsed(collapsed) {
        if (!caseDocumentsBody || !caseDocumentsToggle) return;
        caseDocumentsBody.classList.toggle("collapsed", collapsed);
        caseDocumentsToggle.setAttribute("aria-expanded", (!collapsed).toString());
        if (caseDocumentsChevron) {
            caseDocumentsChevron.classList.toggle("rotated", collapsed);
        }
        const hint = document.getElementById("case-documents-hint");
        if (hint) {
            hint.innerHTML = collapsed ? '<i class="fa-solid fa-caret-down"></i>' : '<i class="fa-solid fa-caret-up"></i>';
        }
    }

    function updateCaseDocumentsBadge() {
        if (caseDocumentsCountBadge) {
            let count = 0;
            if (singleDropZone && singleDropZone.classList.contains("compact")) count += 1;
            if (supportingDocsChips) count += supportingDocsChips.querySelectorAll(".supporting-doc-chip").length;

            if (count > 0) {
                caseDocumentsCountBadge.textContent = String(count);
                caseDocumentsCountBadge.style.display = "inline-flex";
            } else {
                caseDocumentsCountBadge.style.display = "none";
            }
        }
        updateSupportingDocsBadge();
    }

    if (caseDocumentsToggle) {
        caseDocumentsToggle.addEventListener("click", () => {
            const isCollapsed = caseDocumentsBody ? caseDocumentsBody.classList.contains("collapsed") : false;
            setCaseDocumentsCollapsed(!isCollapsed);
        });
    }

    // ==========================================================================
    // SUPPORTING DOCUMENTS: dedicated collapsible dropdown nested below the
    // main court file. Independent from the outer Case Documents collapse so
    // the "Upload Supporting Document" action is never hidden away just
    // because the main file finished processing.
    // ==========================================================================
    const supportingDocsToggle = document.getElementById("supporting-docs-toggle");
    const supportingDocsBody = document.getElementById("supporting-docs-body");
    const supportingDocsChevron = document.getElementById("supporting-docs-chevron");
    const supportingDocsCountBadge = document.getElementById("supporting-docs-count-badge");

    function setSupportingDocsCollapsed(collapsed) {
        if (!supportingDocsBody || !supportingDocsToggle) return;
        supportingDocsBody.classList.toggle("collapsed", collapsed);
        supportingDocsToggle.setAttribute("aria-expanded", (!collapsed).toString());
        if (supportingDocsChevron) {
            supportingDocsChevron.classList.toggle("rotated", collapsed);
        }
        const hint = document.getElementById("supporting-docs-hint");
        if (hint) {
            hint.innerHTML = collapsed ? '<i class="fa-solid fa-caret-down"></i>' : '<i class="fa-solid fa-caret-up"></i>';
        }
    }

    function updateSupportingDocsBadge() {
        if (!supportingDocsCountBadge) return;
        const count = document.getElementById("supporting-docs-chips")
            ? document.getElementById("supporting-docs-chips").querySelectorAll(".supporting-doc-chip").length
            : 0;
        if (count > 0) {
            supportingDocsCountBadge.textContent = String(count);
            supportingDocsCountBadge.style.display = "inline-flex";
        } else {
            supportingDocsCountBadge.style.display = "none";
        }
    }

    if (supportingDocsToggle) {
        supportingDocsToggle.addEventListener("click", () => {
            const isCollapsed = supportingDocsBody ? supportingDocsBody.classList.contains("collapsed") : false;
            setSupportingDocsCollapsed(!isCollapsed);
        });
    }

    // Attach click handler for change-file-btn
    const changeFileBtn = document.getElementById("change-file-btn");
    if (changeFileBtn) {
        changeFileBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            resetSingleUploadUI(true);
        });
    }

    singleDropZone.addEventListener("click", (e) => {
        if (singleDropZone.classList.contains("compact")) {
            return;
        }
        if (e.target === singleFileInput) return;
        singleFileInput.click();
    });

    // --- DRAGGABLE PANEL RESIZER (Case Parameters <-> PDF Preview) ---
    function initCalculatorPanelResizer() {
        const grid = document.querySelector("#tab-calculator .workspace-grid.split-55-45");
        const resizer = document.getElementById("calculator-panel-resizer");
        if (!grid || !resizer) return;

        const MIN_LEFT_PERCENT = 25;
        const MAX_LEFT_PERCENT = 75;

        function setLeftPercent(percent) {
            const clamped = Math.min(MAX_LEFT_PERCENT, Math.max(MIN_LEFT_PERCENT, percent));
            grid.style.setProperty("--split-left", clamped + "%");
        }

        function resetSplit() {
            grid.style.removeProperty("--split-left");
        }

        let dragging = false;

        function onPointerDown(e) {
            dragging = true;
            resizer.classList.add("resizing");
            document.body.classList.add("panel-resize-active");
            e.preventDefault();
        }

        function onPointerMove(e) {
            if (!dragging) return;
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const rect = grid.getBoundingClientRect();
            const percent = ((clientX - rect.left) / rect.width) * 100;
            setLeftPercent(percent);
        }

        function onPointerUp() {
            if (!dragging) return;
            dragging = false;
            resizer.classList.remove("resizing");
            document.body.classList.remove("panel-resize-active");
        }

        resizer.addEventListener("mousedown", onPointerDown);
        resizer.addEventListener("touchstart", onPointerDown, { passive: false });
        window.addEventListener("mousemove", onPointerMove);
        window.addEventListener("touchmove", onPointerMove, { passive: false });
        window.addEventListener("mouseup", onPointerUp);
        window.addEventListener("touchend", onPointerUp);

        resizer.addEventListener("dblclick", (e) => {
            e.preventDefault();
            resetSplit();
        });
    }
    initCalculatorPanelResizer();

    singleFileInput.addEventListener("click", (e) => {
        e.stopPropagation();
    });

    singleFileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleSinglePdfUpload(e.target.files[0]);
        }
    });

    function updatePdfPreview(blobUrl, filename, badgeHtml) {
        window.currentPdfName = filename;
        if (typeof loadPdfNotes === "function") {
            loadPdfNotes(filename);
        }

        if (singlePreviewFilename) {
            singlePreviewFilename.innerHTML = `${filename} ${badgeHtml || ""}`;
        }

        if (singlePreviewContainer) {
            let iframe = singlePreviewContainer.querySelector(".pdf-iframe");
            if (!iframe) {
                iframe = document.createElement("iframe");
                iframe.className = "pdf-iframe";
                iframe.style.width = "100%";
                iframe.style.height = "100%";
                iframe.style.border = "none";
                const canvas = singlePreviewContainer.querySelector("#pdf-annotation-canvas");
                if (canvas) {
                    singlePreviewContainer.insertBefore(iframe, canvas);
                } else {
                    singlePreviewContainer.appendChild(iframe);
                }
            }
            iframe.src = `${blobUrl}#toolbar=0`;
            const emptyState = singlePreviewContainer.querySelector(".preview-empty-state");
            if (emptyState) emptyState.style.display = "none";
        }

        if (singlePreviewCard) {
            singlePreviewCard.classList.remove("hidden-section");
            singlePreviewCard.classList.add("show");
        }
    }

    async function handleSinglePdfUpload(file) {
        window.lastEnhancementVerdict = null;
        window.currentRenderedVerdict = null;
        resetSingleUploadUI(false);
        const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
        if (!isPdf) {
            alert("Please upload a valid legal PDF case document.");
            return;
        }

        // Show the PDF immediately, before OCR even starts, so the person has
        // something useful to read/scroll while extraction runs in the background.
        const immediateBlobUrl = URL.createObjectURL(file);
        try {
            ensureCaseSessionId();
        } catch (e) {
            console.error("Failed to ensure case session id:", e);
        }
        const badgeHtml = `<span class="badge source-badge" id="single-preview-source-badge" style="margin-left: 8px; background: rgba(251, 191, 36, 0.2); color: #f59e0b; border: 1px solid rgba(251, 191, 36, 0.3); font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; display: inline-block;"><i class="fa-solid fa-spinner fa-spin"></i> Extracting...</span>`;
        updatePdfPreview(immediateBlobUrl, file.name, badgeHtml);
        const earlyPdfTabBtn = document.querySelector('.pane-tab-btn[data-pane-tab="pdf"]');
        if (earlyPdfTabBtn) {
            earlyPdfTabBtn.click();
        }

        // Start the Live OCR timer
        startOcrTimer();

        // Show a small, non-blocking "processing" indicator next to the header
        // timer badge. There is no overlay/card over the form anymore — the
        // person can freely scroll the page while OCR runs in the background.
        const headerProcessingBadge = document.getElementById("header-ocr-processing-badge");
        if (headerProcessingBadge) {
            headerProcessingBadge.style.display = "inline-flex";
        }
        const loader = null; // Defined as null to prevent ReferenceErrors in subsequent loader blocks.

        // Per-page monitor state
        const _ocrPages = {};
        let _ocrTotalPages = 0;

        const formData = new FormData();
        formData.append("file", file);
        if (currentCaseSessionId) {
            formData.append("case_session_id", currentCaseSessionId);
        }

        try {
            const response = await fetch("/api/ocr/process-ocr", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                throw new Error("OCR Processing failed");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let partialBuffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                partialBuffer += decoder.decode(value, { stream: true });
                const lines = partialBuffer.split("\n");

                // Keep the last item in the buffer as it might be incomplete
                partialBuffer = lines.pop();

                for (const line of lines) {
                    const cleanLine = line.trim();
                    if (!cleanLine.startsWith("data: ")) continue;

                    const payload = cleanLine.slice(6);
                    const data = JSON.parse(payload);

                    // Update local form panel timer status text (this element already
                    // existed in the form — no separate loader card needed anymore).
                    const statusText = document.getElementById("ocr-timer-status-text");
                    if (statusText && data.message) {
                        statusText.textContent = data.message;
                    }

                    if (data.status === "done") {
                        // Processing finished — hide the small header indicator
                        if (headerProcessingBadge) headerProcessingBadge.style.display = "none";

                        if (data.success) {
                            // Stop timer on success
                            stopOcrTimerSuccess();

                            // Change drop-zone to compact view
                            if (singleDropZone) {
                                singleDropZone.classList.add("compact");
                            }
                            const compactFilename = document.getElementById("compact-filename");
                            if (compactFilename) {
                                compactFilename.textContent = file.name;
                            }
                            const compactDuration = document.getElementById("compact-duration-caption");
                            if (compactDuration) {
                                const elapsedText = document.getElementById("ocr-timer-elapsed");
                                const elapsedVal = elapsedText ? elapsedText.textContent.trim() : "";
                                compactDuration.textContent = elapsedVal ? `(completed in ${elapsedVal})` : "";
                            }

                            // TEMPORARY: Log OCR suggestions structure
                            console.log("OCR suggestions structure:", JSON.stringify(data.suggestions, null, 2));

                            // Cache suggestions and track globally for on-demand autofill
                            window.lastUploadedOcrData = data;
                            window.detectedTrack = data.track || "high_court";

                            // Store raw text for AI data recovery
                            currentOcrRawText = data.raw_text || [];
                            window.lastRawText = currentOcrRawText.join("\n");
                            if (downloadWordBtn) {
                                if (currentOcrRawText.length > 0) {
                                    downloadWordBtn.disabled = false;
                                    downloadWordBtn.style.opacity = "1";
                                    downloadWordBtn.style.cursor = "pointer";
                                } else {
                                    downloadWordBtn.disabled = true;
                                    downloadWordBtn.style.opacity = "0.5";
                                    downloadWordBtn.style.cursor = "not-allowed";
                                }
                            }

                            // The PDF preview was already rendered the moment the file was
                            // selected, so just refresh the little status badge (no re-render).
                            const sourceBadge = document.getElementById("single-preview-source-badge");
                            if (sourceBadge) {
                                sourceBadge.innerHTML = `<i class="fa-solid fa-check"></i> Source: ${data.fallback_source}`;
                                sourceBadge.style.background = "rgba(59, 130, 246, 0.2)";
                                sourceBadge.style.color = "#60a5fa";
                                sourceBadge.style.borderColor = "rgba(59, 130, 246, 0.3)";
                            }
                            singlePreviewCard.classList.remove("hidden-section");
                            singlePreviewCard.classList.add("show");

                            // Programmatically switch active right pane tab to PDF Preview upon successful upload
                            const pdfTabBtn = document.querySelector('.pane-tab-btn[data-pane-tab="pdf"]');
                            if (pdfTabBtn) {
                                pdfTabBtn.click();
                            }

                            // Programmatically open the AI Assistant slide-over chatbot drawer upon successful upload
                            if (aiAssistantTrigger && slideover && !slideover.classList.contains("open")) {
                                aiAssistantTrigger.click();
                            }

                            // Highlight and show the live metrics and precedents cards
                            if (liveMetricsCard) liveMetricsCard.classList.add("show");
                            if (evaluatorCard) evaluatorCard.classList.add("show");
                            if (supportingDocsSection) {
                                supportingDocsSection.style.display = "block";
                            }
                            updateCaseDocumentsBadge();
                            // Keep the Case Documents section expanded -- the main file
                            // switches to its compact one-line view automatically, and the
                            // "Upload Supporting Document" dropdown right below it must stay
                            // visible so the person can immediately attach lower-court /
                            // hospital records without having to hunt for a collapsed panel.



                            const detectedCaseType = data.case_type;
                            const detectedTrack = data.track || "high_court";
                            if (detectedCaseType && (detectedCaseType === "injury" || detectedCaseType === "death")) {
                                caseTypeSelect.value = detectedCaseType;
                                caseTypeSelect.dispatchEvent(new Event("change"));
                                updateEnhancementCheck(data);

                                if (detectedTrack === "lower_court" && detectedCaseType === "injury") {
                                    // Lower-court (tribunal-level) injury judgments don't follow a
                                    // reliable structured format the way death cases or High Court
                                    // Memos do -- auto-extraction is too unsafe to trust here.
                                    // Do NOT autofill. Ask the user to fill the workstation manually.
                                    showToast(
                                        `This looks like a lower-court injury judgment. Auto-fill isn't reliable for this document type -- please fill the workstation fields in manually.`,
                                        "warning",
                                        8000
                                    );
                                } else {
                                    // High Court appeals (any case type) and lower-court death cases
                                    // (which do follow a reliable structured particulars block) are
                                    // safe to auto-fill and auto-calculate.
                                    showToast(`Case PDF analyzed! Auto-filling workstation and running the calculator... (AI-generated — please verify)`, "success");
                                    let autofillSucceeded = false;
                                    window.autofillReadyPromise = (async () => {
                                        if (currentOcrRawText && currentOcrRawText.length > 0) {
                                            autofillSucceeded = await runAiRecovery(currentOcrRawText, data.track);
                                        }
                                        if (!autofillSucceeded) {
                                            applyAllOcrSuggestions(data.suggestions, null, null, null, true, true);
                                        }
                                    })();
                                }
                            } else {
                                showCaseTypeConfirmationPrompt(data, file, false);
                            }
                        } else {
                            stopOcrTimerFailure();
                            showToast("Failed to extract data from the PDF: " + (data.message || "Unknown OCR error."), "error");
                        }
                    } else if (data.status === "failed") {
                        if (headerProcessingBadge) headerProcessingBadge.style.display = "none";
                        stopOcrTimerFailure();
                        showToast("Failed to extract data from the PDF: " + (data.message || "Unknown OCR error."), "error");
                    }
                }
            }
        } catch (error) {
            if (headerProcessingBadge) headerProcessingBadge.style.display = "none";
            stopOcrTimerFailure();
            console.error("Single PDF OCR error:", error);
            showToast(`OCR processing failed: ${error.message}. Please verify the central FastAPI server is fully initialized.`, "error");
        }
    }

    // ==========================================================================
    // BATCH PDF MANAGER (DRAG & DROP + POLLING QUEUE)
    // ==========================================================================

    // Drag events
    ["dragenter", "dragover"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add("dragover");
        }, false);
    });

    dropZone.addEventListener("dragleave", (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove("dragover");
    }, false);

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove("dragover");

        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleBatchUpload(files);
        }
    });

    dropZone.addEventListener("click", (e) => {
        if (e.target === fileInput) return;
        fileInput.click();
    });

    fileInput.addEventListener("click", (e) => {
        e.stopPropagation();
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleBatchUpload(e.target.files);
        }
    });

    // Upload batch files
    async function handleBatchUpload(files) {
        // Start the Live OCR timer for batch processing
        startOcrTimer();
        let validPdfCount = 0;

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
            if (isPdf) {
                validPdfCount++;
                const file_id = "file_" + Math.random().toString(36).substring(2, 12);
                fileQueue.push({
                    file_id: file_id,
                    filename: file.name,
                    status: "queued",
                    progress: 10,
                    suggestions: null,
                    raw_text: []
                });
                // Map local filename to the file object to facilitate local iframe previewing!
                uploadedFileObjects[file.name] = file;
                
                // Process the supporting document asynchronously
                processSupportingDoc(file, file_id);
            }
        }

        if (validPdfCount === 0) {
            alert("No valid PDF files selected. Please upload legal document PDFs.");
            return;
        }

        renderQueueList();
    }

    async function processSupportingDoc(file, file_id) {
        const idx = fileQueue.findIndex(f => f.file_id === file_id);
        if (idx !== -1) {
            fileQueue[idx].status = "scanning";
            fileQueue[idx].progress = 30;
            renderQueueList();
        }

        const formData = new FormData();
        formData.append("file", file);
        if (currentCaseSessionId) {
            formData.append("case_session_id", currentCaseSessionId);
        }

        try {
            const response = await fetch("/api/ocr/process-supporting-doc", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                throw new Error("Failed to process supporting document");
            }

            const data = await response.json();
            
            const idxDone = fileQueue.findIndex(f => f.file_id === file_id);
            if (idxDone !== -1) {
                fileQueue[idxDone].status = "indexed";
                fileQueue[idxDone].progress = 100;
                fileQueue[idxDone].ocr_debug = data.ocr_debug;
                renderQueueList();
            }
        } catch (error) {
            console.error("Error processing supporting doc:", error);
            const idxErr = fileQueue.findIndex(f => f.file_id === file_id);
            if (idxErr !== -1) {
                fileQueue[idxErr].status = "failed";
                fileQueue[idxErr].progress = 100;
                fileQueue[idxErr].error = error.message;
                renderQueueList();
            }
        } finally {
            const activeFiles = fileQueue.filter(f => f.status === "queued" || f.status === "scanning" || f.status === "indexing");
            if (activeFiles.length === 0) {
                stopOcrTimerSuccess();
            }
        }
    }

    // Render queue card lists
    function renderQueueList() {
        if (fileQueue.length === 0) {
            batchFileList.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-box-open"></i>
                    <p>No legal PDFs uploaded yet. Drag and drop PDF claim judgments above to begin centralized vector storage.</p>
                </div>
            `;
            if (queueBadge) queueBadge.classList.add("hidden");
            queueCountLabel.textContent = "0 Files";
            return;
        }

        batchFileList.innerHTML = "";
        if (queueBadge) {
            queueBadge.classList.remove("hidden");
            queueBadge.textContent = fileQueue.length;
        }
        queueCountLabel.textContent = `${fileQueue.length} Files`;

        fileQueue.forEach(file => {
            const item = document.createElement("div");
            item.className = "batch-file-item";
            item.setAttribute("data-id", file.file_id);
            item.setAttribute("data-filename", file.filename);

            const displayTag = {
                queued: `<span class="bf-tag queued">Queued</span>`,
                scanning: `<span class="bf-tag scanning">Scanning</span>`,
                indexing: `<span class="bf-tag indexing">Indexing</span>`,
                indexed: `<span class="bf-tag indexed"><i class="fa-solid fa-circle-check"></i> Indexed</span>`,
                failed: `<span class="bf-tag failed">Failed</span>`
            }[file.status] || `<span class="bf-tag queued">${file.status}</span>`;

            item.innerHTML = `
                <div class="bf-meta">
                    <span class="bf-name" title="${file.filename}">${file.filename}</span>
                    ${displayTag}
                </div>
                <div class="bf-progress-row">
                    <div class="bf-bar-wrapper">
                        <div class="bf-bar-fill" style="width: ${file.progress}%"></div>
                    </div>
                    <span class="bf-pct">${file.progress}%</span>
                </div>
                ${file.status === "indexed" ? `
                    <div class="bf-actions">
                        <button type="button" class="btn btn-small btn-success autofill-queue-btn" data-id="${file.file_id}">
                            <i class="fa-solid fa-arrow-left"></i> Auto-fill form
                        </button>
                        <button type="button" class="btn btn-small btn-danger remove-indexed-btn" data-id="${file.file_id}" data-filename="${file.filename}" title="Remove from database and chat">
                            <i class="fa-solid fa-trash"></i> Remove
                        </button>
                    </div>
                ` : ""}
            `;

            // Bind click to previews
            item.addEventListener("click", (e) => {
                // Prevent trigger if they click action buttons
                if (e.target.closest(".autofill-queue-btn")) return;
                if (e.target.closest(".remove-indexed-btn")) return;

                document.querySelectorAll(".batch-file-item").forEach(c => c.classList.remove("active-preview"));
                item.classList.add("active-preview");
                loadPdfPreview(file.filename);
            });

            batchFileList.appendChild(item);
        });

        // Bind clicks on autofill buttons
        document.querySelectorAll(".autofill-queue-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                const id = btn.getAttribute("data-id");
                const matchedFile = fileQueue.find(f => f.file_id === id);
                if (matchedFile) {
                    window.lastEnhancementVerdict = null;
                    window.currentRenderedVerdict = null;
                    window.lastUploadedOcrData = matchedFile;
                    window.detectedTrack = matchedFile.track || "high_court";
                    currentOcrRawText = matchedFile.raw_text || [];
                    window.lastRawText = currentOcrRawText.join("\n");
                    if (downloadWordBtn) {
                        if (currentOcrRawText.length > 0) {
                            downloadWordBtn.disabled = false;
                            downloadWordBtn.style.opacity = "1";
                            downloadWordBtn.style.cursor = "pointer";
                        } else {
                            downloadWordBtn.disabled = true;
                            downloadWordBtn.style.opacity = "0.5";
                            downloadWordBtn.style.cursor = "not-allowed";
                        }
                    }

                    loadPdfPreview(matchedFile.filename);
                    updateEnhancementCheck(matchedFile);

                    switchTab("calculator");
                    showToast("Queue file loaded! Click the 'Auto-fill Workstation Form' button below the enhancement section to populate the fields.", "success");
                }
            });
        });

        // Bind clicks on remove buttons
        document.querySelectorAll(".remove-indexed-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.preventDefault();
                e.stopPropagation();
                const id = btn.getAttribute("data-id");
                const filename = btn.getAttribute("data-filename");
                if (!confirm(`Remove "${filename}" from the vector database and AI chat?

This cannot be undone.`)) return;

                // Visual feedback — disable button while deleting
                btn.disabled = true;
                btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Removing...`;

                try {
                    const res = await fetch(`/api/qdrant/document/${encodeURIComponent(filename)}`, {
                        method: "DELETE"
                    });
                    const data = await res.json();

                    if (data.success) {
                        // Remove from local fileQueue
                        const idx = fileQueue.findIndex(f => f.file_id === id);
                        if (idx !== -1) fileQueue.splice(idx, 1);

                        showToast(`"${filename}" removed from database.`, "success");
                        renderQueueList();

                        // Re-sync the chat document filter dropdown
                        syncChatDocumentFilter();
                    } else {
                        btn.disabled = false;
                        btn.innerHTML = `<i class="fa-solid fa-trash"></i> Remove`;
                        showToast(`Failed to remove: ${data.detail || "Unknown error"}`, "error");
                    }
                } catch (err) {
                    btn.disabled = false;
                    btn.innerHTML = `<i class="fa-solid fa-trash"></i> Remove`;
                    showToast(`Network error while removing file.`, "error");
                }
            });
        });

        // Sync chatbot document filter select options
        syncChatDocumentFilter();
    }

    // Automatically perform OCR autofill and AI data recovery (combined batch pipeline)
    function performFullAutofill(matchedFile) {
        if (!matchedFile.suggestions) {
            showToast("No pre-parsed heuristic data available for this file.", "warning");
            return;
        }

        stopOcrTimerSuccess();

        // Store raw text for AI data recovery
        currentOcrRawText = matchedFile.raw_text || [];
        if (downloadWordBtn) {
            if (currentOcrRawText.length > 0) {
                downloadWordBtn.disabled = false;
                downloadWordBtn.style.opacity = "1";
                downloadWordBtn.style.cursor = "pointer";
            } else {
                downloadWordBtn.disabled = true;
                downloadWordBtn.style.opacity = "0.5";
                downloadWordBtn.style.cursor = "not-allowed";
            }
        }

        // Update workstation preview card with the batch-loaded PDF if possible
        const fileObj = uploadedFileObjects[matchedFile.filename];
        if (fileObj && singlePreviewContainer && singlePreviewFilename) {
            const blobUrl = URL.createObjectURL(fileObj);
            const badgeHtml = `<span class="badge source-badge" style="margin-left: 8px; background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; display: inline-block;">Source: Batch Library</span>`;
            updatePdfPreview(blobUrl, matchedFile.filename, badgeHtml);
        }

        const caseType = matchedFile.suggestions ? matchedFile.suggestions.case_type : null;
        if (caseType && (caseType === "injury" || caseType === "death")) {
            caseTypeSelect.value = caseType;
            caseTypeSelect.dispatchEvent(new Event("change"));
            applyAllOcrSuggestions(matchedFile.suggestions, null, null, null, true, true);
            window.lastRawText = (matchedFile.raw_text || []).join("\n");
            switchTab("calculator");
            if (currentOcrRawText.length > 0) {
                runAiRecovery(currentOcrRawText);
            }
        } else {
            showCaseTypeConfirmationPrompt(matchedFile, fileObj, true);
        }
    }

    // Modal prompt for ambiguous case types
    function showCaseTypeConfirmationPrompt(data, fileObj = null, isBatch = false) {
        // Create modal overlay
        const overlay = document.createElement("div");
        overlay.id = "case-type-confirmation-overlay";
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(15, 23, 42, 0.7);
            backdrop-filter: blur(8px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 99999;
        `;

        const card = document.createElement("div");
        card.style.cssText = `
            background: var(--bg-panel, #1e293b);
            border: 1px solid var(--border-glass, rgba(255,255,255,0.08));
            border-radius: var(--radius-md, 12px);
            padding: 30px;
            width: 90%;
            max-width: 480px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4);
            text-align: center;
            display: flex;
            flex-direction: column;
            gap: 20px;
        `;

        card.innerHTML = `
            <div>
                <i class="fa-solid fa-circle-question" style="font-size: 3.5rem; color: var(--color-warning, #f59e0b); margin-bottom: 15px; display: inline-block;"></i>
                <h3 style="font-size: 1.25rem; font-weight: 700; color: var(--text-primary, #fff); margin-bottom: 8px;">Case Type Ambiguous</h3>
                <p style="font-size: 0.88rem; color: var(--text-secondary, #94a3b8); line-height: 1.5; margin: 0 0 15px 0;">
                    The OCR system could not confidently determine if this is an Injury or Death case. Please select the correct case type to continue:
                </p>
            </div>
            <div style="display: flex; gap: 12px; justify-content: center; margin-top: 10px;">
                <button id="confirm-injury-btn" class="btn" style="flex: 1; padding: 12px; font-weight: 700; display: flex; flex-direction: column; align-items: center; gap: 8px; background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3); color: #60a5fa; cursor: pointer; border-radius: 8px; transition: all 0.2s ease;">
                    <i class="fa-solid fa-user-injured" style="font-size: 1.5rem;"></i>
                    Injury Case
                </button>
                <button id="confirm-death-btn" class="btn" style="flex: 1; padding: 12px; font-weight: 700; display: flex; flex-direction: column; align-items: center; gap: 8px; background: rgba(244, 63, 94, 0.15); border: 1px solid rgba(244, 63, 94, 0.3); color: #fb7185; cursor: pointer; border-radius: 8px; transition: all 0.2s ease;">
                    <i class="fa-solid fa-skull" style="font-size: 1.5rem;"></i>
                    Death Case
                </button>
            </div>
        `;

        overlay.appendChild(card);
        document.body.appendChild(overlay);

        const injBtn = card.querySelector("#confirm-injury-btn");
        const dthBtn = card.querySelector("#confirm-death-btn");

        injBtn.addEventListener("mouseenter", () => {
            injBtn.style.background = "rgba(59, 130, 246, 0.25)";
            injBtn.style.borderColor = "#60a5fa";
        });
        injBtn.addEventListener("mouseleave", () => {
            injBtn.style.background = "rgba(59, 130, 246, 0.15)";
            injBtn.style.borderColor = "rgba(59, 130, 246, 0.3)";
        });

        dthBtn.addEventListener("mouseenter", () => {
            dthBtn.style.background = "rgba(244, 63, 94, 0.25)";
            dthBtn.style.borderColor = "#fb7185";
        });
        dthBtn.addEventListener("mouseleave", () => {
            dthBtn.style.background = "rgba(244, 63, 94, 0.15)";
            dthBtn.style.borderColor = "rgba(244, 63, 94, 0.3)";
        });

        function handleSelect(type) {
            overlay.remove();
            caseTypeSelect.value = type;
            caseTypeSelect.dispatchEvent(new Event("change"));

            if (isBatch) {
                if (data.suggestions) {
                    data.suggestions.case_type = type;
                    applyAllOcrSuggestions(data.suggestions, null, null, null, true, true);
                }
                switchTab("calculator");
                if (currentOcrRawText.length > 0) {
                    runAiRecovery(currentOcrRawText);
                }
            } else {
                if (data.suggestions) {
                    data.suggestions.case_type = type;
                    applyAllOcrSuggestions(data.suggestions, null, null, null, false, true);
                    updateEnhancementCheck(data);
                }
                showToast(`Form updated for ${type === "injury" ? "Injury" : "Death"} Case!`, "success");
            }
        }

        injBtn.addEventListener("click", () => handleSelect("injury"));
        dthBtn.addEventListener("click", () => handleSelect("death"));
    }

    // Open Autofill Selection Modal to choose between OCR and AI Deep Extraction
    function showAutofillChoiceModal(matchedFile) {
        const choiceModal = document.getElementById("autofill-choice-modal");
        if (!choiceModal) return;

        const quickBtn = document.getElementById("btn-quick-autofill");
        const aiBtn = document.getElementById("btn-ai-autofill");
        const cancelBtn = document.getElementById("dismiss-autofill-choice-btn");
        const closeBtn = document.getElementById("close-autofill-choice-btn");

        // Clone buttons to clear previous event listeners cleanly
        const newQuickBtn = quickBtn.cloneNode(true);
        const newAiBtn = aiBtn.cloneNode(true);
        quickBtn.parentNode.replaceChild(newQuickBtn, quickBtn);
        aiBtn.parentNode.replaceChild(newAiBtn, aiBtn);

        // Bind quick OCR path
        newQuickBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            choiceModal.classList.remove("open");
            if (matchedFile.suggestions) {
                stopOcrTimerSuccess();

                // Store raw text for AI data recovery
                currentOcrRawText = matchedFile.raw_text || [];
                if (downloadWordBtn) {
                    if (currentOcrRawText.length > 0) {
                        downloadWordBtn.disabled = false;
                        downloadWordBtn.style.opacity = "1";
                        downloadWordBtn.style.cursor = "pointer";
                    } else {
                        downloadWordBtn.disabled = true;
                        downloadWordBtn.style.opacity = "0.5";
                        downloadWordBtn.style.cursor = "not-allowed";
                    }
                }

                // Update workstation preview card with the batch-loaded PDF if possible
                const fileObj = uploadedFileObjects[matchedFile.filename];
                if (fileObj && singlePreviewContainer && singlePreviewFilename) {
                    const blobUrl = URL.createObjectURL(fileObj);
                    const badgeHtml = `<span class="badge source-badge" style="margin-left: 8px; background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; display: inline-block;">Source: Batch Library</span>`;
                    updatePdfPreview(blobUrl, matchedFile.filename, badgeHtml);
                }

                applyAllOcrSuggestions(matchedFile.suggestions);

                window.lastRawText = (matchedFile.raw_text || []).join("\n");


                switchTab("calculator");
            } else {
                showToast("No pre-parsed heuristic data available for this file.", "warning");
            }
        });

        // Bind AI LLM Deep Extraction path
        newAiBtn.addEventListener("click", async (e) => {
            e.stopPropagation();

            // Validate that we have raw text before attempting LLM recovery
            const rawTextLines = matchedFile.raw_text || [];
            if (rawTextLines.length === 0) {
                showToast("No raw OCR text is available for this file to perform AI recovery.", "warning");
                choiceModal.classList.remove("open");
                return;
            }

            choiceModal.classList.remove("open");

            // Set currentOcrRawText from batch file
            currentOcrRawText = rawTextLines;
            window.lastRawText = currentOcrRawText.join("\n");


            if (downloadWordBtn) {
                if (currentOcrRawText.length > 0) {
                    downloadWordBtn.disabled = false;
                    downloadWordBtn.style.opacity = "1";
                    downloadWordBtn.style.cursor = "pointer";
                } else {
                    downloadWordBtn.disabled = true;
                    downloadWordBtn.style.opacity = "0.5";
                    downloadWordBtn.style.cursor = "not-allowed";
                }
            }

            // Update workstation preview card with the batch-loaded PDF if possible
            const fileObj = uploadedFileObjects[matchedFile.filename];
            if (fileObj && singlePreviewContainer && singlePreviewFilename) {
                const blobUrl = URL.createObjectURL(fileObj);
                const badgeHtml = `<span class="badge source-badge" style="margin-left: 8px; background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; display: inline-block;">Source: Batch Library</span>`;
                updatePdfPreview(blobUrl, matchedFile.filename, badgeHtml);
            }

            // Switch to workstation tab
            switchTab("calculator");

            // Show spinning loader overlay in workstation panel
            const formPanel = document.querySelector("#tab-calculator .panel.scroll-y");
            if (!formPanel) return;

            const loader = document.createElement("div");
            loader.className = "form-ocr-loader";
            loader.innerHTML = `
                <div class="spinner-glow"></div>
                <p>AI Legal LLM is parsing text...</p>
                <span style="font-size: 0.8rem; color: var(--text-secondary); opacity: 0.8;">Recovering missing legal compensation entities</span>
            `;
            formPanel.style.position = "relative";
            formPanel.appendChild(loader);

            try {
                // Call backend
                const response = await fetch("/api/ocr/ai-recover", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ 
                        raw_text: currentOcrRawText,
                        case_session_id: currentCaseSessionId
                    })
                });

                loader.remove();

                if (!response.ok) {
                    const errData = await response.json().catch(() => ({}));
                    throw new Error(errData.detail || "AI recovery API returned error status");
                }
                const data = await response.json();

                if (data.success) {
                    const confidenceScores = data.raw_recovered ? data.raw_recovered.confidence_scores : null;
                    const ocrEvidence = data.raw_recovered ? data.raw_recovered.ocr_evidence_case : null;

                    // Apply suggestions exactly the same way as clicking "Ask LLM to Extract" manually
                    applyAllOcrSuggestions(data.suggestions, confidenceScores, ocrEvidence, data.raw_recovered);
                    showToast("AI data extraction complete! All recovered parameters cached internally.", "success");
                } else {
                    showToast("AI extraction failed to extract fields.", "error");
                }
            } catch (error) {
                if (loader) loader.remove();
                console.error("AI recovery failed:", error);
                showToast(`AI extraction failed: ${error.message}`, "error");
            }
        });

        // Close on cancel/close
        const closeHandler = (e) => {
            if (e) e.stopPropagation();
            choiceModal.classList.remove("open");
        };
        cancelBtn.onclick = closeHandler;
        closeBtn.onclick = closeHandler;

        // Open modal
        choiceModal.classList.add("open");
    }

    // Close choice modal when clicking outside content area
    window.addEventListener("click", (e) => {
        const choiceModal = document.getElementById("autofill-choice-modal");
        if (e.target === choiceModal) {
            choiceModal.classList.remove("open");
        }
    });

    // High-Fidelity local Blob URL previewing
    function loadPdfPreview(filename) {
        const fileObj = uploadedFileObjects[filename];
        if (!fileObj) {
            previewContainer.innerHTML = `
                <div class="preview-empty-state">
                    <i class="fa-solid fa-triangle-exclamation" style="font-size: 3rem; color: var(--color-warning);"></i>
                    <p>PDF file context lost. Please select a freshly uploaded PDF or re-upload to preview.</p>
                </div>
            `;
            previewFilenameBadge.classList.add("hidden");
            return;
        }

        // Generate instant in-memory Blob URL for local PDF rendering
        const blobUrl = URL.createObjectURL(fileObj);

        previewFilenameBadge.classList.remove("hidden");
        previewFilenameBadge.textContent = filename;

        previewContainer.innerHTML = `
            <iframe class="pdf-iframe" src="${blobUrl}#toolbar=0" width="100%" height="100%"></iframe>
        `;
    }

    // Batch Status Polling Loop
    function startQueuePolling() {
        if (isPolling) return;
        isPolling = true;

        const pollInterval = setInterval(async () => {
            // Only poll if we have queued/active files
            const activeFiles = fileQueue.filter(f => f.status === "queued" || f.status === "scanning" || f.status === "indexing");
            if (activeFiles.length === 0) {
                stopOcrTimerSuccess();
                clearInterval(pollInterval);
                isPolling = false;
                return;
            }

            try {
                const response = await fetch("/api/ocr/batch-status");
                if (response.ok) {
                    const data = await response.json();

                    // Sync backend statuses with local queue
                    data.queue.forEach(srvItem => {
                        const localIndex = fileQueue.findIndex(f => f.file_id === srvItem.file_id);
                        if (localIndex !== -1) {
                            fileQueue[localIndex].status = srvItem.status;
                            fileQueue[localIndex].progress = srvItem.progress;
                            fileQueue[localIndex].suggestions = srvItem.suggestions;
                            fileQueue[localIndex].raw_text = srvItem.raw_text;
                            fileQueue[localIndex].ocr_debug = srvItem.ocr_debug;
                        }
                    });

                    renderQueueList();
                }
            } catch (error) {
                console.error("Queue status polling failed:", error);
            }
        }, 1500);
    }

    // Converts a date string coming from OCR heuristics or the AI/LLM extractor
    // (which may arrive as DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY, or already as
    // YYYY-MM-DD) into the exact "YYYY-MM-DD" shape required by
    // <input type="date">. Browsers silently reject anything else, which is
    // why dates would sometimes appear to "not fill" at all. Returns "" if
    // the value can't be confidently parsed as a date.
    function toHtmlDateValue(val) {
        if (!val || typeof val !== "string") return "";
        const trimmed = val.trim();

        // Already ISO (YYYY-MM-DD) — pass through untouched.
        if (/^\d{4}-\d{1,2}-\d{1,2}$/.test(trimmed)) {
            const [y, m, d] = trimmed.split("-");
            return `${y}-${m.padStart(2, "0")}-${d.padStart(2, "0")}`;
        }

        // DD-MM-YYYY, DD/MM/YYYY, or DD.MM.YYYY (day-first, standard in
        // Indian legal documents).
        const dmy = trimmed.match(/^(\d{1,2})[\-/.](\d{1,2})[\-/.](\d{4})$/);
        if (dmy) {
            const day = dmy[1].padStart(2, "0");
            const month = dmy[2].padStart(2, "0");
            const year = dmy[3];
            return `${year}-${month}-${day}`;
        }

        return "";
    }

    // Helper to populate fields based on active case type (Part 5 & Part 6)
    function populateFieldsForActiveCaseType() {
        // Never bail out entirely just because a case type hasn't been
        // resolved yet — the "common" fields below (name, DOB, age, income,
        // accident date, place) apply to both injury and death cases and
        // should always autofill. Only the case-specific extra fields
        // (further below) stay gated on actually knowing injury vs death.
        const activeCaseType = caseTypeSelect.value;

        // Clear all previous low-confidence warning labels, styles, and AI metadata badges again to refresh
        document.querySelectorAll(".verification-warning").forEach(el => el.remove());
        document.querySelectorAll(".low-confidence-input").forEach(el => el.classList.remove("low-confidence-input"));
        document.querySelectorAll(".ai-metadata-badge:not([data-field='case_type'])").forEach(el => el.remove());

        // Field definitions and mapping to DOM input IDs
        // Always Populate (Part 6)
        const commonMapping = {
            "name": "name",
            "father_name": "father-name",
            "date_of_birth": "date-of-birth",
            "age": "age",
            "monthly_income": "monthly-income",
            "date_of_accident": "date-of-accident",
            "place_of_accident": "place-of-accident",
            "dependents": "dependents"
        };

        // Injury Specific (Part 6)
        const injuryMapping = {
            "medical_expenses": "medical-expenses",
            "future_medical_expenses": "future-medical-expenses",
            "pain_and_suffering": "pain-and-suffering",
            "transportation": "transportation",
            "special_diet": "special-diet",
            "attender_charges": "attender-charges",
            "loss_of_income": "loss-of-income",
            "disability": "disability",
            "coliti": "coliti",
            "misex": "misex",
            "loamiti": "loamiti",
            "lopmarri": "lopmarri",
            "loexlife": "loexlife",
            "loveaff": "loveaff",
            "lossofenjoy": "lossofenjoy"
        };

        // Death Specific (Part 6) - mirrors PHP REQUEST fields: loc, loa, fe, conlum, conspo etc.
        const deathMapping = {
            "consortium": "consortium",
            "funeral_expenses": "funeral-expenses",
            "loss_estate": "loss-estate",
            "marital_status": "marital-status",
            "future_type": "future-type",
            "claimant_relationship_to_deceased": "claimant-relationship-display",
            "claimant_relationship_type": "claimant-relationship-type-hidden",
            "conspo": "conspo",
            "conwif": "conwif",
            "conhus": "conhus",
            "conpar": "conpar",
            "conchil": "conchil",
            "conmo": "conmo",
            "confath": "confath",
            "conbro": "conbro",
            "consis": "consis",
            "conlum": "conlum"
        };

        // Prune the cached field values of the opposite case type to avoid stale states
        if (activeCaseType === "injury") {
            Object.keys(deathMapping).forEach(key => {
                delete lastExtractedFields[key];
            });
        } else if (activeCaseType === "death") {
            Object.keys(injuryMapping).forEach(key => {
                delete lastExtractedFields[key];
            });
        }

        // Helper to populate a single DOM element based on key, inputId, and active status
        function populateField(cacheKey, inputId, isAllowed) {
            const el = document.getElementById(inputId);
            if (!el) return;

            const parent = el.closest(".form-group");
            if (parent) {
                const existingReason = parent.querySelector(".custom-empty-reason");
                if (existingReason) existingReason.remove();
                const existingWarning = parent.querySelector(".verification-warning");
                if (existingWarning) existingWarning.remove();
                const existingNote = parent.querySelector(".estimated-note");
                if (existingNote) existingNote.remove();
            }
            el.classList.remove("not-stated-input");
            el.classList.remove("low-confidence-input");

            if (!isAllowed) {
                // Reset/clear value if not allowed to avoid carrying over stale data
                el.value = "";
                el.dispatchEvent(new Event("input"));
                el.dispatchEvent(new Event("change"));
                return;
            }

            const val = lastExtractedFields[cacheKey];

            if (val === undefined || val === null || val === "") {
                if (lastExtractedReasons[cacheKey]) {
                    const reason = lastExtractedReasons[cacheKey];
                    if (parent && !parent.querySelector(".custom-empty-reason")) {
                        const reasonEl = document.createElement("span");
                        reasonEl.className = "custom-empty-reason";
                        reasonEl.style.color = "#f59e0b"; // Warning color
                        reasonEl.style.fontSize = "0.75rem";
                        reasonEl.style.fontWeight = "600";
                        reasonEl.style.marginTop = "4px";
                        reasonEl.style.display = "block";
                        reasonEl.innerHTML = `<i class="fa-solid fa-circle-question"></i> Not Stated: ${reason}`;
                        parent.appendChild(reasonEl);
                    }
                    el.classList.add("not-stated-input");
                }
                return;
            }

            // Check confidence score before populating field value
            const conf = lastExtractedConfidences[cacheKey];
            const threshold = parseFloat(localStorage.getItem("autofill_confidence_threshold") || "0.75");
            if (conf !== undefined && conf !== null && conf < threshold) {
                const reason = lastExtractedReasons[cacheKey] || "";
                if (reason.includes("computed via")) {
                    // Keep the number visible
                    if (inputId === "date-of-birth" || inputId === "date-of-accident") {
                        const htmlDate = toHtmlDateValue(val);
                        if (htmlDate) el.value = htmlDate;
                    } else {
                        el.value = val;
                    }
                    el.dispatchEvent(new Event("input"));
                    el.dispatchEvent(new Event("change"));

                    // Show small, non-blocking note: "Estimated — not found in document text"
                    const parent = el.closest(".form-group");
                    if (parent && !parent.querySelector(".estimated-note")) {
                        const note = document.createElement("span");
                        note.className = "estimated-note";
                        note.style.color = "#64748b"; // muted slate color
                        note.style.fontSize = "0.7rem";
                        note.style.fontStyle = "italic";
                        note.style.marginTop = "2px";
                        note.style.display = "block";
                        note.innerHTML = `<i class="fa-solid fa-circle-info"></i> Estimated — not found in document text`;
                        parent.appendChild(note);
                    }
                } else {
                    el.value = "";
                    el.classList.add("low-confidence-input");
                    
                    const parent = el.closest(".form-group");
                    if (parent && !parent.querySelector(".verification-warning")) {
                        const warning = document.createElement("span");
                        warning.className = "verification-warning";
                        warning.style.color = "#f59e0b";
                        warning.style.fontSize = "0.75rem";
                        warning.style.fontWeight = "600";
                        warning.style.marginTop = "4px";
                        warning.style.display = "block";
                        warning.innerHTML = `<i class="fa-solid fa-circle-info"></i> Low confidence (${Math.round(conf * 100)}%) — left blank for manual entry`;
                        parent.appendChild(warning);
                    }
                    return;
                }
            }

            // Direct Auto-fill only when confidence is high (>= threshold)
            if (inputId === "date-of-birth" || inputId === "date-of-accident") {
                const htmlDate = toHtmlDateValue(val);
                if (htmlDate) {
                    el.value = htmlDate;
                }
            } else {
                el.value = val;
                if (inputId === "dependents") {
                    const claimantsEl = document.getElementById("consortium_claimants");
                    if (claimantsEl && (!claimantsEl.value || claimantsEl.value === "1")) {
                        claimantsEl.value = val;
                        claimantsEl.dispatchEvent(new Event("input"));
                        claimantsEl.dispatchEvent(new Event("change"));
                    }
                    const modeEl = document.getElementById("consortium_mode");
                    if (modeEl && Number(val) > 1) {
                        modeEl.value = "satinder_kaur";
                        modeEl.dispatchEvent(new Event("input"));
                        modeEl.dispatchEvent(new Event("change"));
                    }
                }
            }
            el.dispatchEvent(new Event("input"));
            el.dispatchEvent(new Event("change"));

            // Auto-expand containing collapsible section if value populated
            const collapsibleParent = el.closest(".collapsible-section");
            if (collapsibleParent) {
                collapsibleParent.style.display = "grid";
                collapsibleParent.classList.remove("hidden-section");
            }

        }
        // Run population for all common fields
        Object.keys(commonMapping).forEach(cacheKey => {
            populateField(cacheKey, commonMapping[cacheKey], true);
        });

        // Run population for Injury specific fields
        const isInjury = (activeCaseType === "injury");
        Object.keys(injuryMapping).forEach(cacheKey => {
            populateField(cacheKey, injuryMapping[cacheKey], isInjury);
        });

        // Run population for Death specific fields
        const isDeath = (activeCaseType === "death");
        Object.keys(deathMapping).forEach(cacheKey => {
            populateField(cacheKey, deathMapping[cacheKey], isDeath);
        });

        updateLiveCalculations();
    }

    // Helper to update the visual Audit Log (Part 7)
    function updateAuditLog(userCase, llmCase, ocrEvidence, avgConfidence, overwriteBlocked) {
        const userCaseVal = document.getElementById("audit-val-user-case");
        const llmCaseVal = document.getElementById("audit-val-llm-case");
        const ocrEvidenceVal = document.getElementById("audit-val-ocr-evidence");
        const confidenceVal = document.getElementById("audit-val-confidence");
        const overwriteBlockedVal = document.getElementById("audit-val-overwrite-blocked");
        const terminal = document.getElementById("audit-log-terminal");

        const displayMap = {
            "injury": "Injury Case",
            "death": "Death Case",
            "None Selected": "None Selected",
            "Unspecified": "Unspecified"
        };

        if (userCaseVal) userCaseVal.textContent = displayMap[userCase] || userCase;
        if (llmCaseVal) llmCaseVal.textContent = displayMap[llmCase] || llmCase;
        if (ocrEvidenceVal) {
            ocrEvidenceVal.textContent = ocrEvidence;
            if (ocrEvidence === "INJURY") {
                ocrEvidenceVal.style.color = "#34d399";
            } else if (ocrEvidence === "DEATH") {
                ocrEvidenceVal.style.color = "#f43f5e";
            } else {
                ocrEvidenceVal.style.color = "#f59e0b";
            }
        }
        if (confidenceVal) confidenceVal.textContent = (avgConfidence * 100).toFixed(1) + "%";

        if (overwriteBlockedVal) {
            overwriteBlockedVal.textContent = overwriteBlocked ? "TRUE" : "FALSE";
            if (overwriteBlocked) {
                overwriteBlockedVal.style.color = "#ef4444";
                overwriteBlockedVal.className = "value text-glow";
            } else {
                overwriteBlockedVal.style.color = "#10b981";
                overwriteBlockedVal.className = "value";
            }
        }

        if (terminal) {
            const timestamp = new Date().toLocaleTimeString();
            const logMsg = document.createElement("div");
            logMsg.style.marginBottom = "4px";

            if (overwriteBlocked) {
                logMsg.innerHTML = `<span style="color: #ef4444;">[${timestamp}] [WARN] Overwrite Blocked!</span> Manual Case Type '${displayMap[userCase]}' preserved over predicted '${displayMap[llmCase]}'.`;
            } else {
                logMsg.innerHTML = `<span style="color: #34d399;">[${timestamp}] [AUDIT]</span> Applied suggestions. User: ${displayMap[userCase]} | LLM: ${displayMap[llmCase]} | OCR: ${ocrEvidence}.`;
            }

            if (terminal.children.length > 20) {
                terminal.removeChild(terminal.children[0]);
            }

            terminal.appendChild(logMsg);
            terminal.scrollTop = terminal.scrollHeight;
        }
    }

    // Apply parsed suggestions
    function applyAllOcrSuggestions(suggestions, confidenceScores = null, ocrEvidence = null, rawRecovered = null, isSilent = false, autoCalculate = true) {
        if (!suggestions) return;

        // Normalize flat suggestions into expected nested structure
        if (suggestions && !suggestions.fields) {
            const { case_type, low_confidence_fields, ocr_quality_insufficient,
                ocr_warning, partial_extraction_recovery_mode,
                fallback_source_used, award_amount, total_compensation,
                ai_recovery_triggered, ...fieldValues } = suggestions;
            suggestions = {
                case_type: case_type,
                fields: fieldValues,
                low_confidence_fields: low_confidence_fields || [],
                ocr_quality_insufficient: ocr_quality_insufficient,
                ocr_warning: ocr_warning,
                fallback_source_used: fallback_source_used
            };
        }
        updateEnhancementCheck({ suggestions: suggestions });

        // Clear all previous low-confidence warning labels, styles, and AI metadata badges
        document.querySelectorAll(".verification-warning").forEach(el => el.remove());
        document.querySelectorAll(".custom-empty-reason").forEach(el => el.remove());
        document.querySelectorAll(".low-confidence-input").forEach(el => el.classList.remove("low-confidence-input"));
        document.querySelectorAll(".not-stated-input").forEach(el => el.classList.remove("not-stated-input"));
        document.querySelectorAll(".ai-metadata-badge").forEach(el => el.remove());
        lastExtractedReasons = {};

        // Extract case type (Part 1 Manual case lock)
        let suggestionsCaseType = suggestions.case_type;
        const currentCaseType = caseTypeSelect.value;
        let overwriteBlocked = false;
        let loggedUserCaseType = currentCaseType || "None Selected";
        let loggedLlmCaseType = suggestionsCaseType || "Unspecified";

        if (currentCaseType && currentCaseType !== "") {
            if (suggestionsCaseType && suggestionsCaseType !== currentCaseType) {
                overwriteBlocked = true;

                // Show interactive suggestion badge under case type dropdown
                const parent = caseTypeSelect.closest(".form-group");
                if (parent) {
                    const badge = document.createElement("div");
                    badge.className = "suggested-badge ai-metadata-badge";
                    badge.setAttribute("data-field", "case_type");

                    const displayVal = suggestionsCaseType === "injury" ? "Injury Case" : "Death Case";
                    // Find confidence score for case_type if available, default to 95%
                    let conf = 0.95;
                    if (confidenceScores && confidenceScores.case_type) {
                        conf = confidenceScores.case_type.confidence !== undefined
                            ? confidenceScores.case_type.confidence
                            : confidenceScores.case_type;
                    } else if (suggestions.confidence_scores && suggestions.confidence_scores.case_type) {
                        conf = suggestions.confidence_scores.case_type.confidence !== undefined
                            ? suggestions.confidence_scores.case_type.confidence
                            : suggestions.confidence_scores.case_type;
                    }
                    conf = typeof conf === "number" ? conf : parseFloat(conf) || 0.95;
                    if (conf > 1.0) conf = conf / 100.0;

                    badge.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Suggest: ${displayVal} (${Math.round(conf * 100)}%)`;

                    badge.addEventListener("click", () => {
                        caseTypeSelect.value = suggestionsCaseType;
                        caseTypeSelect.dispatchEvent(new Event("change"));
                        badge.remove();
                        showToast(`Switched to suggested Case Type: ${displayVal}!`, "success");
                    });

                    parent.appendChild(badge);
                }
            }
            suggestionsCaseType = currentCaseType;
        } else {
            if (suggestionsCaseType) {
                caseTypeSelect.value = suggestionsCaseType;
                caseTypeSelect.dispatchEvent(new Event("change"));
            } else {
                console.warn("[WARN] case_type is null or undefined. Prompting user for manual selection.");
                showCaseTypeConfirmationPrompt({ suggestions: suggestions }, null, false);
            }
        }

        // Cache all fields (Part 5 & Part 6)
        const fields = suggestions.fields || {};

        Object.keys(fields).forEach(key => {
            lastExtractedFields[key] = fields[key];
        });

        // Capture the age extraction source so the chatbot knows which part
        // of the document it came from (Particulars Block, OCR fallback, etc.)
        if (suggestions.confidence_scores && suggestions.confidence_scores.age && suggestions.confidence_scores.age.source) {
            lastExtractedFields["age_source"] = suggestions.confidence_scores.age.source;
        }

        // ── Alias normalisation: map LLM/heuristic field name variants to
        //    the canonical keys that injuryMapping/deathMapping expect ──────
        const fieldAliases = {
            "disability_percentage": "disability",
            "permanent_disability": "disability",
            "accident_date": "date_of_accident",
            "dob": "date_of_birth",
            "accident_place": "place_of_accident",
            "loss_of_consortium": "consortium",
            "loss_of_estate": "loss_estate",
            "loss_estate": "loss_estate",
            "funeral": "funeral_expenses",
            "claimant_name": "name",
            "injured_name": "name",
            "deceased_name": "name",
        };
        Object.keys(fieldAliases).forEach(src => {
            const dst = fieldAliases[src];
            if ((fields[src] !== undefined && fields[src] !== null && fields[src] !== "") &&
                (lastExtractedFields[dst] === undefined || lastExtractedFields[dst] === null || lastExtractedFields[dst] === "")) {
                lastExtractedFields[dst] = fields[src];
            }
        });

        ["date_of_birth", "date_of_accident"].forEach(key => {
            if (fields[key]) {
                lastExtractedFields[key] = fields[key];
            }
        });

        // Ensure canonical "name" key is populated from specific name keys
        if (fields.injured_name) lastExtractedFields["name"] = fields.injured_name;
        if (fields.deceased_name) lastExtractedFields["name"] = fields.deceased_name;
        if (fields.claimant_name) lastExtractedFields["name"] = fields.claimant_name;

        // Merge raw recovered details if LLM is executed (Part 5 offline store)
        if (rawRecovered) {
            const keyMappings = {
                "claimant_name": "name",
                "deceased_name": "name",
                "injured_name": "name",
                "father_name": "father_name",
                "place_of_accident": "place_of_accident",
                "accident_place": "place_of_accident",
                "age": "age",
                "monthly_income": "monthly_income",
                "dependents": "dependents",
                "marital_status": "marital_status",
                "future_prospect": "future_prospect",
                "future_type": "future_type",
                "disability": "disability",
                "disability_percentage": "disability",
                "medical_expenses": "medical_expenses",
                "future_medical_expenses": "future_medical_expenses",
                "pain_and_suffering": "pain_and_suffering",
                "transportation": "transportation",
                "special_diet": "special_diet",
                "attender_charges": "attender_charges",
                "loss_of_income": "loss_of_income",
                "loss_of_consortium": "consortium",
                "consortium": "consortium",
                "funeral_expenses": "funeral_expenses",
                "loss_of_estate": "loss_estate",
                "loss_estate": "loss_estate",
                "dob": "date_of_birth",
                "date_of_birth": "date_of_birth",
                "accident_date": "date_of_accident",
                "date_of_accident": "date_of_accident"
            };

            Object.keys(keyMappings).forEach(rawKey => {
                const cacheKey = keyMappings[rawKey];
                const rawObj = rawRecovered[rawKey];
                let val = null;
                let conf = null;
                let reason = null;

                if (rawObj && typeof rawObj === "object" && "value" in rawObj) {
                    val = rawObj.value;
                    conf = rawObj.confidence;
                    reason = rawObj.reason;
                } else if (rawObj !== undefined) {
                    val = rawObj;
                }

                if (val !== null && val !== undefined && val !== "") {
                    lastExtractedFields[cacheKey] = val;
                    if (conf !== null && conf !== undefined) {
                        lastExtractedConfidences[cacheKey] = conf;
                    }
                }
                if (reason) {
                    lastExtractedReasons[cacheKey] = reason;
                }
            });
        }

        // Cache confidences
        const lowConfFields = suggestions.low_confidence_fields || [];
        const combinedKeys = new Set([...Object.keys(lastExtractedFields), "date_of_birth", "date_of_accident"]);

        combinedKeys.forEach(key => {
            if (confidenceScores && confidenceScores[key]) {
                const confVal = confidenceScores[key].confidence !== undefined
                    ? confidenceScores[key].confidence
                    : confidenceScores[key];
                lastExtractedConfidences[key] = typeof confVal === "number" ? confVal : parseFloat(confVal) || 1.0;
                
                if (confidenceScores[key] && confidenceScores[key].reason) {
                    lastExtractedReasons[key] = confidenceScores[key].reason;
                }
            } else if (lastExtractedConfidences[key] === undefined) {
                lastExtractedConfidences[key] = lowConfFields.includes(key) ? 0.65 : 1.0;
            }
        });

        // Run case-specific field population (Part 5 & Part 6)
        console.log("Suggestions received in applyAllOcrSuggestions:", suggestions);
        populateFieldsForActiveCaseType();

        // Telemetry Audit log update (Part 7)
        let evidenceStr = ocrEvidence || "UNCLEAR";
        if (rawRecovered && rawRecovered.ocr_evidence_case) {
            evidenceStr = rawRecovered.ocr_evidence_case;
        }

        let totalConf = 0;
        let confCount = 0;
        Object.keys(lastExtractedConfidences).forEach(k => {
            if (lastExtractedFields[k] !== undefined && lastExtractedFields[k] !== "") {
                totalConf += lastExtractedConfidences[k];
                confCount++;
            }
        });
        const avgConf = confCount > 0 ? (totalConf / confCount) : 0.85;

        updateAuditLog(loggedUserCaseType, loggedLlmCaseType, evidenceStr, avgConf, overwriteBlocked);

        if (!isSilent) {
            if (overwriteBlocked) {
                showToast(`Preserved manually selected Case Type (${loggedUserCaseType})! Overwrite blocked.`, "warning");
            } else {
                showToast(`Workstation variables successfully auto-filled!`, "success");
            }
        }

        // Auto trigger automatic recalculation after autofill is completed (Task 18)
        if (autoCalculate) {
            setTimeout(() => {
                console.log("AUTO RECALCULATING after OCR autofill...");
                if (compensationForm) {
                    compensationForm.dispatchEvent(new Event("submit"));
                }
            }, 500);
        }
    }

    // ==========================================================================
    // AI DATA RECOVERY (LLM OPTIMIZED PARSING EXTRACTION)
    // ==========================================================================
    // AI DATA RECOVERY (LLM OPTIMIZED PARSING EXTRACTION) (Part 3, Part 4 & Part 5 integration)
    // Runs automatically right after every OCR completion (no manual button) —
    // called from handleSinglePdfUpload's success branch below.
    async function runAiRecovery(rawTextLines, track = "high_court") {
        if (!rawTextLines || rawTextLines.length === 0) return;

        // Idempotency guard: the LLM calls behind /ai-recover aren't temperature-0,
        // so a fresh call on the SAME document can legitimately come back worded
        // differently each time. Rather than relying on the backend's cache
        // (which only helps if the process never restarts/evicts), just don't
        // ask again for text we've already summarized in this session.
        const signature = rawTextLines.join("\n");
        if (lastAiRecoverySignature === signature && lastAiRecoveryResult) {
            const data = lastAiRecoveryResult;
            const confidenceScores = data.raw_recovered ? data.raw_recovered.confidence_scores : null;
            const ocrEvidence = data.raw_recovered ? data.raw_recovered.ocr_evidence_case : null;
            applyAllOcrSuggestions(data.suggestions, confidenceScores, ocrEvidence, data.raw_recovered, true);
            showToast("Using the previously generated summary for this document — it won't change on re-click.", "info");
            return true;
        }

        const formPanel = document.querySelector("#tab-calculator .panel.scroll-y");
        const loader = document.createElement("div");
        loader.className = "form-ocr-loader";
        loader.innerHTML = `
            <div class="spinner-glow"></div>
            <p>AI Legal LLM is refining extracted fields...</p>
            <span style="font-size: 0.8rem; color: var(--text-secondary); opacity: 0.8;">Recovering missing legal compensation entities</span>
        `;
        if (formPanel) {
            formPanel.style.position = "relative";
            formPanel.appendChild(loader);
        }

        try {
            const response = await fetch("/api/ocr/ai-recover", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    raw_text: rawTextLines, 
                    track: track,
                    case_session_id: currentCaseSessionId
                })
            });

            loader.remove();

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                const detail = errData.detail || "";
                console.warn("Automatic AI extraction unavailable:", detail || response.status);
                showToast("AI field refinement unavailable — heuristic OCR extraction is already applied.", "warning");
                return false;
            }
            const data = await response.json();

            if (data.success) {
                const confidenceScores = data.raw_recovered ? data.raw_recovered.confidence_scores : null;
                const ocrEvidence = data.raw_recovered ? data.raw_recovered.ocr_evidence_case : null;
                applyAllOcrSuggestions(data.suggestions, confidenceScores, ocrEvidence, data.raw_recovered, true);

                // Memoize so a repeat click on the same document reuses this result
                lastAiRecoverySignature = signature;
                lastAiRecoveryResult = data;

                showToast("Case analyzed — fields auto-filled and refined by AI.", "success");
                return true;
            } else {
                showToast("AI extraction could not recover additional fields.", "warning");
                return false;
            }
        } catch (error) {
            loader.remove();
            console.error("Automatic AI recovery failed:", error);
            showToast("AI field refinement failed — heuristic OCR extraction is already applied.", "warning");
            return false;
        }
    }

    if (downloadWordBtn) {
        downloadWordBtn.addEventListener("click", async () => {
            if (!currentOcrRawText || currentOcrRawText.length === 0) {
                showToast("No raw OCR text available. Please upload a PDF first.", "warning");
                return;
            }

            const originalContent = downloadWordBtn.innerHTML;
            downloadWordBtn.disabled = true;
            downloadWordBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Generating...`;

            try {
                let filename = "extracted_text";
                if (singlePreviewFilename && singlePreviewFilename.innerHTML) {
                    const parts = singlePreviewFilename.innerHTML.split("<span");
                    let cleanFilename = parts[0].trim();
                    if (cleanFilename && cleanFilename !== "No File Loaded") {
                        if (cleanFilename.toLowerCase().endsWith(".pdf")) {
                            filename = cleanFilename.slice(0, -4);
                        } else {
                            filename = cleanFilename;
                        }
                    }
                }

                const response = await fetch("/api/ocr/download-docx", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        raw_text: currentOcrRawText,
                        filename: filename
                    })
                });

                if (!response.ok) {
                    throw new Error(`Server returned error status ${response.status}`);
                }

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = filename.endsWith(".docx") ? filename : `${filename}.docx`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                showToast("Word document downloaded successfully!", "success");
            } catch (error) {
                console.error("Failed to download Word document:", error);
                showToast(`Failed to download Word document: ${error.message}`, "error");
            } finally {
                downloadWordBtn.disabled = false;
                downloadWordBtn.innerHTML = originalContent;
            }
        });
    }

    function syncChatDocumentFilter() {
        const chatDocumentFilter = document.getElementById("chat-document-filter");
        if (!chatDocumentFilter) return;

        const currentSelection = chatDocumentFilter.value;

        chatDocumentFilter.innerHTML = '<option value="all">All Documents</option>';

        const indexedFiles = fileQueue.filter(f => f.status === "indexed").map(f => f.filename);

        const uniqueFiles = [...new Set(indexedFiles)];
        uniqueFiles.forEach(filename => {
            const opt = document.createElement("option");
            opt.value = filename;
            opt.textContent = filename;
            chatDocumentFilter.appendChild(opt);
        });

        if (uniqueFiles.includes(currentSelection)) {
            chatDocumentFilter.value = currentSelection;
        }
    }

    // ==========================================================================
    // AI PRECEDENTS SEARCH & CHAT (TAB 3)
    // ==========================================================================
    chatSendBtn.addEventListener("click", handleChatSend);
    chatInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") handleChatSend();
    });
    if (clearPrecedentChatBtn) {
        clearPrecedentChatBtn.addEventListener("click", () => {
            precedentChatHistory = [];
            chatMessages.innerHTML = `
                <div class="chat-bubble bot">
                    <div class="chat-avatar"><i class="fa-solid fa-robot"></i></div>
                    <div class="chat-text">
                        Hello! I am your **AI Legal Assistant** coupled with your centralized **Qdrant Vector Database**.
                        <br><br>
                        Once you index legal files in the **PDF Library**, you can ask me semantic questions such as:
                        <ul>
                            <li>*"Find cases where an unmarried deceased of age 32 had 4 dependents"*</li>
                            <li>*"Show me injury judgments with permanent disability above 40%"*</li>
                            <li>*"What compensation was awarded in cases involving salary of Rs 25,000?"*</li>
                        </ul>
                        I will automatically locate matching sentences in Qdrant, retrieve the judgments, and formulate legal summaries!
                    </div>
                </div>
            `;
        });
    }

    async function handleChatSend() {
        const query = chatInput.value.trim();
        if (!query) return;

        // Render user message bubble
        appendChatBubble(query, "user");
        chatInput.value = "";

        // Render thinking loader bubble
        const loadingId = appendChatBubble(`<i class="fa-solid fa-spinner fa-spin"></i> Semantic AI searching Qdrant database...`, "bot", true);

        try {
            const payload = {
                message: query,
                case_type: chatCaseFilter.value,
                history: precedentChatHistory.slice(-12),
                case_session_id: currentCaseSessionId
            };

            const chatDocumentFilter = document.getElementById("chat-document-filter");
            const docFilterVal = chatDocumentFilter ? chatDocumentFilter.value : "all";
            if (docFilterVal !== "all") {
                payload.filename = docFilterVal;
            }

            const response = await fetch("/api/chat/pdf", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error("Search API failure");
            const data = await response.json();

            // Remove loading bubble
            document.getElementById(loadingId).remove();

            // Render structured markdown legal response
            appendChatBubble(data.response, "bot");

            // Update chat memory
            precedentChatHistory.push({ role: "user", content: query });
            precedentChatHistory.push({ role: "assistant", content: data.response });

        } catch (error) {
            console.error("AI Legal chat error:", error);
            document.getElementById(loadingId).remove();
            appendChatBubble("I apologize, but I encountered an error searching the centralized database. Please verify the backend uvicorn service is fully initialized.", "bot");
        }
    }

    function appendChatBubble(text, sender, isLoader = false) {
        const bubble = document.createElement("div");
        const id = `msg_${Date.now()}`;
        bubble.id = id;
        bubble.className = `chat-bubble ${sender}`;

        const avatarHtml = sender === "bot" ? `<i class="fa-solid fa-robot"></i>` : `<i class="fa-solid fa-user-tie"></i>`;

        // Render markdown formatting inside bubble text (simple converter)
        let formattedText = text;
        if (!isLoader) {
            formattedText = text
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/\n/g, '<br>');
        }

        bubble.innerHTML = `
            <div class="chat-avatar">${avatarHtml}</div>
            <div class="chat-text">${formattedText}</div>
        `;

        chatMessages.appendChild(bubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        if (!isLoader && typeof bindChatBubbleClick === "function") {
            bindChatBubbleClick(bubble);
        }

        return id;
    }

    // ==========================================================================
    // COMPARATIVE LEGAL EVALUATOR (TAB 1)
    // ==========================================================================
    if (triggerEvalBtn) {
        triggerEvalBtn.addEventListener("click", async () => {
            if (!currentCalculationAmount || currentCalculationAmount <= 0) {
                alert("Please calculate the compensation first by filling in mandatory workstation variables and clicking 'Calculate'.");
                return;
            }

            // Display loading loader inside evaluator card body
            if (evaluatorCardBody) {
                evaluatorCardBody.innerHTML = `
                    <div class="empty-state" style="padding: 10px 0;">
                        <i class="fa-solid fa-spinner fa-spin fa-2x" style="color: var(--color-primary);"></i>
                        <p>Generating query embeddings & fetching precedents from Qdrant vector database...</p>
                    </div>
                `;
            }

            const payload = {
                params: {
                    case_type: caseTypeSelect.value,
                    age: parseInt(ageInput.value) || 0,
                    monthly_income: parseFloat(monthlyIncomeInput.value) || 0,
                    dependents: parseInt(dependentsInput.value) || 0,
                    marital_status: maritalStatusSelect.value || "married",
                    deduction_override: document.getElementById("death-deduction")?.value || "auto",
                    future_type: parseInt(futureTypeSelect?.value || 2),
                    future_prospect: (() => { const fp = document.getElementById("future-prospect"); const v = fp ? fp.value : null; return (v !== null && v !== "" && v !== "0") ? parseFloat(v) : null; })(),
                    consortium: document.getElementById("consortium")?.value ? parseFloat(document.getElementById("consortium").value) : null,
                    funeral_expenses: document.getElementById("funeral-expenses")?.value ? parseFloat(document.getElementById("funeral-expenses").value) : null,
                    loss_estate: document.getElementById("loss-estate")?.value ? parseFloat(document.getElementById("loss-estate").value) : null,
                    disability: parseFloat(document.getElementById("disability")?.value || 0)
                },
                calculated_amount: currentCalculationAmount
            };

            try {
                const response = await fetch("/api/search/evaluate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error("Comparative evaluation API error");
                const data = await response.json();

                if (!data.success || !data.evaluation) {
                    throw new Error(data.message || "Failed to generate evaluation");
                }

                renderPrecedentEvaluation(data.evaluation);

            } catch (error) {
                console.error("Benchmarking evaluation failed:", error);
                alert("Failed to benchmark precedents on server. Running simulated evaluation analysis.");
                // Offline fallback evaluator
                const fallbackEvaluation = simulateEvaluationMath(payload);
                renderPrecedentEvaluation(fallbackEvaluation);
            }
        });
    }

    function simulateEvaluationMath(req) {
        const cal = req.calculated_amount;
        const avg = cal * (0.93 + Math.random() * 0.12);
        const margin = ((cal - avg) / avg) * 100;

        return {
            calculated_amount: cal,
            average_precedent_award: Math.round(avg),
            margin_percent: Math.round(margin * 100) / 100,
            alignment: Math.abs(margin) <= 5.0 ? "aligned" : (margin > 5.0 ? "high" : "low"),
            recommendation: Math.abs(margin) <= 5.0
                ? `Calculated award is extremely well-aligned with precedents (${margin > 0 ? '+' : ''}${margin.toFixed(1)}% margin).`
                : `Calculated award is ${Math.abs(margin).toFixed(1)}% ${margin > 0 ? 'higher' : 'lower'} than precedent averages.`,
            insurance_defense: `Historically claims of similar profiles average around Rs. ${Math.round(avg).toLocaleString('en-IN')}.`,
            claimant_argument: `Judicial precedents reach up to Rs. ${Math.round(avg * 1.1).toLocaleString('en-IN')}.`,
            precedents: [
                { filename: "judgment_mact_2023.pdf", score: 0.89, name: "Late Ram Sharan", details: "Age: 32 | Income: Rs. 22,000", award_amount: Math.round(avg * 0.95) },
                { filename: "hc_fatal_indore_2022.pdf", score: 0.84, name: "Late Suresh Verma", details: "Age: 35 | Income: Rs. 27,000", award_amount: Math.round(avg * 1.05) }
            ]
        };
    }

    function renderPrecedentEvaluation(evalData) {
        const alignLabels = {
            aligned: `<span class="eval-badge aligned"><i class="fa-solid fa-circle-check"></i> Aligned</span>`,
            high: `<span class="eval-badge high"><i class="fa-solid fa-triangle-exclamation"></i> High Valuation</span>`,
            low: `<span class="eval-badge low"><i class="fa-solid fa-arrow-down-long"></i> Under-valued</span>`
        };

        let precedentsHtml = "";
        evalData.precedents.forEach(p => {
            precedentsHtml += `
                <div class="precedent-mini-card">
                    <div class="pm-info">
                        <span class="pm-name">${p.name}</span>
                        <span class="pm-details" title="${p.filename}">${p.filename} | ${p.details}</span>
                    </div>
                    <div>
                        <span class="pm-award">Rs. ${p.award_amount.toLocaleString('en-IN')}</span>
                        <span class="pm-score">${(p.score * 100).toFixed(1)}% Match</span>
                    </div>
                </div>
            `;
        });

        if (evaluatorCardBody) {
            evaluatorCardBody.innerHTML = `
                <!-- Hero comparative stats -->
                <div class="eval-hero">
                    <div class="eval-stats">
                        <span class="label">Calculated Award</span>
                        <span class="value">Rs. ${evalData.calculated_amount.toLocaleString('en-IN')}</span>
                    </div>
                    <div class="eval-stats" style="text-align: right;">
                        <span class="label">Precedent Avg</span>
                        <span class="value" style="color: var(--text-secondary)">Rs. ${evalData.average_precedent_award.toLocaleString('en-IN')}</span>
                    </div>
                </div>

                <!-- Alignment and margin -->
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
                    <span class="card-text">Award Margin: <strong>${evalData.margin_percent > 0 ? '+' : ''}${evalData.margin_percent}%</strong></span>
                    ${alignLabels[evalData.alignment] || ""}
                </div>

                <!-- Legal recommendation -->
                <div class="eval-desc">
                    <strong><i class="fa-solid fa-gavel"></i> Legal Opinion:</strong><br>
                    ${evalData.recommendation}
                </div>

                <!-- Legal Argument briefs -->
                <div class="eval-desc" style="background: rgba(186, 104, 200, 0.02); border-color: rgba(186, 104, 200, 0.12); margin-top: 8px;">
                    <strong><i class="fa-solid fa-scroll"></i> Court Brief Argument:</strong><br>
                    <em>"${evalData.claimant_argument}"</em>
                </div>

                <!-- Retrieved precedent list -->
                <div style="margin-top: 14px;">
                    <span class="metric-label">Matching Cases Indexed (Qdrant)</span>
                    ${precedentsHtml}
                </div>
            `;
        }

        if (typeof triggerTabNotification === "function") {
            triggerTabNotification("benchmarking");
        }
    }

    // ==========================================================================
    // FORM CALCULATOR API SUBMISSION
    // ==========================================================================
    compensationForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        console.log("CALCULATE CLICKED");

        const caseType = caseTypeSelect.value;
        if (!caseType) {
            showToast("Please select a case type first!", "warning");
            return;
        }

        // Validate all required inputs are filled prior to calculations
        compensationForm.querySelectorAll(".form-group").forEach(grp => {
            grp.classList.remove("has-error");
        });

        if (!compensationForm.reportValidity()) {
            const invalidFields = compensationForm.querySelectorAll("input:invalid, select:invalid");
            invalidFields.forEach(field => {
                const grp = field.closest(".form-group");
                if (grp) {
                    grp.classList.add("has-error");
                    
                    if (field.id === "age") {
                        let reason = lastExtractedReasons["age"] || "No age or DOB was found in the text";
                        let reasonSpan = grp.querySelector(".custom-empty-reason");
                        if (!reasonSpan) {
                            reasonSpan = document.createElement("span");
                            reasonSpan.className = "custom-empty-reason";
                            reasonSpan.style.fontSize = "0.75rem";
                            reasonSpan.style.fontWeight = "600";
                            reasonSpan.style.marginTop = "4px";
                            reasonSpan.style.display = "block";
                            grp.appendChild(reasonSpan);
                        }
                        reasonSpan.style.color = "#ef4444";
                        reasonSpan.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> <strong>Missing from document:</strong> ${reason}`;
                    }
                }
            });
            clearCalculatedOutputs();
            showToast("Please fill all mandatory case fields before calculating.", "warning");
            return;
        }

        // Before submitting, check if age is missing
        const ageVal = parseInt(ageInput.value);
        if (!ageVal || ageVal <= 0) {
            showToast("⚠️ Age not set — calculation will use default age 30. Upload a PDF or enter DOB + accident date.", "warning");
        }

        const payload = {
            case_type: caseType,
            age: Number(ageInput.value || 0),
            monthly_income: Number(monthlyIncomeInput.value || 0),
            date_of_accident: document.getElementById("date-of-accident")?.value || null,

            dependents: Number(dependentsInput.value || 0),
            marital_status: maritalStatusSelect.value || "married",
            deduction_override: document.getElementById("death-deduction")?.value || "auto",
            future_type: Number(futureTypeSelect?.value || 2),
            future_prospect: (() => { const fp = document.getElementById("future-prospect"); const v = fp ? fp.value : null; return (v !== null && v !== "" && v !== "0") ? Number(v) : null; })(),
            consortium: document.getElementById("consortium")?.value ? Number(document.getElementById("consortium").value) : null,
            funeral_expenses: document.getElementById("funeral-expenses")?.value ? Number(document.getElementById("funeral-expenses").value) : null,
            loss_estate: document.getElementById("loss-estate")?.value ? Number(document.getElementById("loss-estate").value) : null,
            consortium_claimants: document.getElementById("consortium_claimants")?.value ? Number(document.getElementById("consortium_claimants").value) : 1,
            consortium_mode: document.getElementById("consortium_mode")?.value || "flat",

            // Consortium sub-heads read from form
            conlum: Number(document.getElementById("conlum")?.value || 0),
            conspo: Number(document.getElementById("conspo")?.value || 0),
            conpar: Number(document.getElementById("conpar")?.value || 0),
            conchil: Number(document.getElementById("conchil")?.value || 0),
            conwif: Number(document.getElementById("conwif")?.value || 0),
            conmo: Number(document.getElementById("conmo")?.value || 0),
            confath: Number(document.getElementById("confath")?.value || 0),
            conhus: Number(document.getElementById("conhus")?.value || 0),
            conbro: Number(document.getElementById("conbro")?.value || 0),
            consis: Number(document.getElementById("consis")?.value || 0),

            disability: Number(document.getElementById("disability")?.value || 0),
            medical_expenses: Number(document.getElementById("medical-expenses")?.value || 0),
            future_medical_expenses: Number(document.getElementById("future-medical-expenses")?.value || 0),
            pain_and_suffering: Number(document.getElementById("pain-and-suffering")?.value || 0),
            transportation: Number(document.getElementById("transportation")?.value || 0),
            special_diet: Number(document.getElementById("special-diet")?.value || 0),
            attender_charges: Number(document.getElementById("attender-charges")?.value || 0),
            loss_of_income: Number(document.getElementById("loss-of-income")?.value || 0),

            // Extra Injury heads read from form
            coliti: Number(document.getElementById("coliti")?.value || 0),
            misex: Number(document.getElementById("misex")?.value || 0),
            loamiti: Number(document.getElementById("loamiti")?.value || 0),
            lopmarri: Number(document.getElementById("lopmarri")?.value || 0),
            loexlife: Number(document.getElementById("loexlife")?.value || 0),
            loveaff: Number(document.getElementById("loveaff")?.value || 0),
            lossofenjoy: Number(document.getElementById("lossofenjoy")?.value || 0)
        };

        try {
            const response = await fetch("/api/calculate/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error("Server calculator returned error status");
            const results = await response.json();

            if (results.success === false) {
                throw new Error(results.error || "Server calculation process failed");
            }

            // Align with nested schema: use results.breakdown if available, otherwise flat results
            const breakdown = results.breakdown || results;
            currentCalculationAmount = results.total_compensation || breakdown.final_amount || 0;
            currentCalculationBreakdown = breakdown;

            // Update inputs and previews with real calculated money values
            updateMonetaryOutputs(breakdown);

            renderResultsDashboard(breakdown, payload);
            openModal();
            showToast("Compensation calculated successfully via FastAPI server!", "success");

            // Enable Evaluator button
            if (triggerEvalBtn) triggerEvalBtn.disabled = false;

        } catch (error) {
            console.error("Server-side calculation failed:", error);
            showToast(`Backend computation failed: ${error.message}. Running local mathematical fallback engine.`, "warning");

            const localResults = calculateCompensationLocally(payload);

            currentCalculationAmount = localResults.final_amount;
            currentCalculationBreakdown = localResults;

            // Update inputs and previews with real calculated money values locally
            updateMonetaryOutputs(localResults);

            renderResultsDashboard(localResults, payload);
            openModal();
            if (triggerEvalBtn) triggerEvalBtn.disabled = false;
        }
    });

    // Clear validation error styling on input change
    compensationForm.addEventListener("input", (e) => {
        const target = e.target;
        if (target && (target.tagName === "INPUT" || target.tagName === "SELECT")) {
            const grp = target.closest(".form-group");
            if (grp && grp.classList.contains("has-error")) {
                if (target.checkValidity()) {
                    grp.classList.remove("has-error");
                }
            }
        }
    });

    // Local Math Evaluator fallback
    function calculateCompensationLocally(data) {
        const age = data.age;
        const multiplier = getMultiplier(age);
        const monthly = data.monthly_income;
        const annual = monthly * 12;

        if (data.case_type === "death") {
            const futureProspect = getFutureProspectPercentage(age, data.future_type);
            const futureProspectAmount = monthly * futureProspect / 100;
            const enhancedMonthlyIncome = monthly + futureProspectAmount;
            const annualIncome = enhancedMonthlyIncome * 12;
            const deductionRatio = getDeductionRatio(data.dependents, data.marital_status);
            const deductionPercent = Math.round(deductionRatio * 100);
            const deductionAmount = annualIncome * deductionRatio;
            const dependencyIncome = annualIncome - deductionAmount;
            const lossOfDependency = dependencyIncome * multiplier;

            const conlum = Number(data.conlum || 0);
            const conspo = Number(data.conspo || 0);
            const conpar = Number(data.conpar || 0);
            const conchil = Number(data.conchil || 0);
            const conwif = Number(data.conwif || 0);
            const conmo = Number(data.conmo || 0);
            const confath = Number(data.confath || 0);
            const conhus = Number(data.conhus || 0);
            const conbro = Number(data.conbro || 0);
            const consis = Number(data.consis || 0);
            const consortium_breakdown_total = conlum + conspo + conpar + conchil + conwif + conmo + confath + conhus + conbro + consis;
            
            function getConventionalHeadsEnhanced(baseAmount, referenceDateStr) {
                let refDate = null;
                if (referenceDateStr) {
                    let parts = referenceDateStr.split(/[-/]/);
                    if (parts.length === 3) {
                        if (parts[0].length === 4) {
                            refDate = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
                        } else {
                            refDate = new Date(Number(parts[2]), Number(parts[1]) - 1, Number(parts[0]));
                        }
                    }
                }
                if (!refDate || isNaN(refDate.getTime())) {
                    refDate = new Date();
                }

                const anchorDate = new Date(2017, 9, 31);
                if (refDate <= anchorDate) {
                    return baseAmount;
                }

                let yearsElapsed = refDate.getFullYear() - anchorDate.getFullYear();
                if (refDate.getMonth() < anchorDate.getMonth() || 
                    (refDate.getMonth() === anchorDate.getMonth() && refDate.getDate() < anchorDate.getDate())) {
                    yearsElapsed -= 1;
                }
                const periods = Math.floor(yearsElapsed / 3);
                return Math.round(baseAmount * (1.10 ** periods) * 100) / 100;
            }

            function getVal(val, defaultVal) {
                if (val === undefined || val === null || val === "" || isNaN(Number(val))) {
                    return defaultVal;
                }
                return Number(val);
            }

            const refDateStr = data.award_date || data.date_of_accident;
            const consortiumDefault = getConventionalHeadsEnhanced(40000.0, refDateStr);
            const funeralDefault = getConventionalHeadsEnhanced(15000.0, refDateStr);
            const lossEstateDefault = getConventionalHeadsEnhanced(15000.0, refDateStr);
            const consortiumPerPerson = getVal(data.consortium, consortiumDefault);

            let consortiumClaimantsVal = Number(data.consortium_claimants);
            if (isNaN(consortiumClaimantsVal) || consortiumClaimantsVal <= 0) {
                consortiumClaimantsVal = 1;
            }

            const consortiumMode = (data.consortium_mode || "flat").trim().toLowerCase();
            let consortium = consortiumPerPerson;
            if (consortiumMode === "satinder_kaur" || consortiumMode === "per_lr" || consortiumMode === "per_heir") {
                consortium = consortiumPerPerson * consortiumClaimantsVal;
            }

            let consortiumSettled = consortium;
            let consortiumContested = 0;

            if (consortium_breakdown_total > 0) {
                consortium = 0;
            }
            const funeral_expenses = getVal(data.funeral_expenses, funeralDefault);
            const loss_estate = getVal(data.loss_estate, lossEstateDefault);
            const medical_expenses = Number(data.medical_expenses || 0);

            const finalCompensation = lossOfDependency + consortium + funeral_expenses + loss_estate + consortium_breakdown_total + medical_expenses;

            return {
                case_type: "death",
                multiplier: multiplier,
                future_prospect_percentage: Math.round(futureProspect),
                future_prospect_amount: Math.round(futureProspectAmount),
                enhanced_monthly_income: Math.round(enhancedMonthlyIncome),
                monthly_income: Math.round(monthly),
                annual_income: Math.round(annualIncome),
                future_income: Math.round(annualIncome), // for backwards compatibility
                deduction_percentage: Math.round(deductionPercent),
                deduction_amount: Math.round(deductionAmount),
                dependency_income: Math.round(dependencyIncome),
                loss_of_dependency: Math.round(lossOfDependency),
                consortium: consortium,
                funeral_expenses: funeral_expenses,
                loss_estate: loss_estate,
                medical_expenses: medical_expenses,
                conlum: conlum,
                conspo: conspo,
                conpar: conpar,
                conchil: conchil,
                conwif: conwif,
                conmo: conmo,
                confath: confath,
                conhus: conhus,
                conbro: conbro,
                consis: consis,
                consortium_breakdown_total: Math.round(consortium_breakdown_total),
                final_compensation: Math.round(finalCompensation),
                final_amount: Math.round(finalCompensation)
            };
        } else {
            const disabilityCompensation = annual * (data.disability / 100) * multiplier;
            
            const medical_expenses = Number(data.medical_expenses || 0);
            const future_medical_expenses = Number(data.future_medical_expenses || 0);
            const pain_and_suffering = Number(data.pain_and_suffering || 0);
            const transportation = Number(data.transportation || 0);
            const special_diet = Number(data.special_diet || 0);
            const attender_charges = Number(data.attender_charges || 0);
            const loss_of_income = Number(data.loss_of_income || 0);

            const coliti = Number(data.coliti || 0);
            const misex = Number(data.misex || 0);
            const loamiti = Number(data.loamiti || 0);
            const lopmarri = Number(data.lopmarri || 0);
            const loexlife = Number(data.loexlife || 0);
            const loveaff = Number(data.loveaff || 0);
            const lossofenjoy = Number(data.lossofenjoy || 0);

            const finalCompensation = disabilityCompensation + medical_expenses + future_medical_expenses +
                pain_and_suffering + transportation + special_diet + attender_charges + loss_of_income +
                coliti + misex + loamiti + lopmarri + loexlife + loveaff + lossofenjoy;

            return {
                case_type: "injury",
                multiplier: multiplier,
                annual_income: Math.round(annual),
                future_income_loss: Math.round(disabilityCompensation),
                medical_expenses: medical_expenses,
                future_medical_expenses: future_medical_expenses,
                pain_and_suffering: pain_and_suffering,
                transportation: transportation,
                special_diet: special_diet,
                attender_charges: attender_charges,
                loss_of_income: loss_of_income,
                coliti: coliti,
                misex: misex,
                loamiti: loamiti,
                lopmarri: lopmarri,
                loexlife: loexlife,
                loveaff: loveaff,
                lossofenjoy: lossofenjoy,
                final_amount: Math.round(finalCompensation)
            };
        }
    }

    function formatCurrency(amount) {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 0
        }).format(amount);
    }

    function updateMonetaryOutputs(res) {
        if (res.case_type === "death") {
            const annualIncome = res.annual_income || 0;
            const enhancedMonthlyIncome = res.enhanced_monthly_income || 0;
            const deductionPercent = res.deduction_percentage || 0;
            const deductionAmount = res.deduction_amount || 0;
            const mult = res.multiplier || 0;
            const lossOfDependency = res.loss_of_dependency || 0;
            const finalComp = res.final_compensation || res.final_amount || 0;

            // Populate read-only inputs
            const lossDepInput = document.getElementById("loss-of-dependency");
            if (lossDepInput) lossDepInput.value = Math.round(lossOfDependency);

            const finalDeathCompInput = document.getElementById("death-final-compensation");
            if (finalDeathCompInput) finalDeathCompInput.value = Math.round(finalComp);

            // Populate dynamic dashboard elements
            if (document.getElementById("live-calc-annual")) {
                document.getElementById("live-calc-annual").textContent = formatCurrency(annualIncome);
                document.getElementById("live-calc-future").textContent = formatCurrency(enhancedMonthlyIncome);
                document.getElementById("live-calc-deduct-pct").textContent = `${deductionPercent}%`;
                document.getElementById("live-calc-deduct-amt").textContent = formatCurrency(deductionAmount);
                document.getElementById("live-calc-multiplier").textContent = mult;
                document.getElementById("live-calc-dependency").textContent = formatCurrency(lossOfDependency);
                document.getElementById("live-calc-total").textContent = formatCurrency(finalComp);
            }
        }
    }

    function clearCalculatedOutputs() {
        const lossDepInput = document.getElementById("loss-of-dependency");
        if (lossDepInput) lossDepInput.value = "";

        const finalDeathCompInput = document.getElementById("death-final-compensation");
        if (finalDeathCompInput) finalDeathCompInput.value = "";

        const liveCalcIds = [
            "live-calc-annual", "live-calc-future", "live-calc-deduct-pct", 
            "live-calc-deduct-amt", "live-calc-multiplier", "live-calc-dependency", 
            "live-calc-total"
        ];
        liveCalcIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = "—";
        });
    }


    // ==========================================================================
    // ENHANCEMENT CHECK RENDERER
    // ==========================================================================
    function updateEnhancementCheck(data) {
        let classification = null;
        if (data) {
            if (data.suggestions && data.suggestions.case_classification) {
                classification = data.suggestions.case_classification;
            } else if (data.case_classification) {
                classification = data.case_classification;
            } else if (data.suggestions && data.suggestions.fields && data.suggestions.fields.case_classification) {
                classification = data.suggestions.fields.case_classification;
            } else if (data.fields && data.fields.case_classification) {
                classification = data.fields.case_classification;
            }
        }

        // Cache the last valid case classification
        if (classification && classification.verdict && classification.verdict !== "not_determinable") {
            window.lastEnhancementVerdict = classification;
        }

        // Preserve previous valid classification if the new one is empty or not determinable
        if ((!classification || classification.verdict === "not_determinable") && window.lastEnhancementVerdict) {
            classification = window.lastEnhancementVerdict;
        }

        const container = document.getElementById("case-type-suggestion");
        if (!container) return;

        container.classList.remove("hidden-section");

        const track = data?.track || data?.ocr_debug?.track?.track || window.detectedTrack || "high_court";

        let innerHTML = "";

        if (track === "lower_court") {
            innerHTML = `
                <div style="display: flex; flex-direction: column; gap: 12px; align-items: center; justify-content: center; text-align: center;">
                    <span style="font-size: 0.85rem; font-weight: 700; color: var(--text-primary); text-transform: uppercase; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 8px; width: 100%;">Enhancement Verdict</span>
                    <div style="font-size: 0.9rem; font-weight: 700; color: var(--color-warning); margin: 8px 0; display: flex; align-items: center; gap: 8px;">
                        <i class="fa-solid fa-circle-exclamation"></i> Not applicable as file is of lower court
                    </div>
                </div>
            `;
        } else {
            const VERDICT_LABELS = {
                enhancement: { text: "Appeal for Enhancement", color: "var(--color-success)" },
                reduction: { text: "Appeal for Reduction", color: "var(--color-warning)" },
                not_determinable: { text: "Not Determinable", color: "var(--text-secondary)" }
            };

            const verdict = (classification && classification.verdict) || "not_determinable";
            const oldVerdict = window.currentRenderedVerdict || "none/empty";
            if (oldVerdict !== verdict) {
                window.currentRenderedVerdict = verdict;
                const err = new Error();
                const stackLine = err.stack ? err.stack.split("\n")[2] : "unknown caller";
                console.log(`[ENHANCEMENT VERDICT CHANGE] Old: "${oldVerdict}" -> New: "${verdict}". Triggered by: ${stackLine.trim()}`);
            }

            const label = VERDICT_LABELS[verdict] || VERDICT_LABELS.not_determinable;
            const confidencePct = classification ? Math.round((classification.confidence || 0) * 100) : 0;

            let basisNote = "";
            if (classification) {
                if (classification.basis === "conflict") {
                    basisNote = `Grounds of Appeal and Prayer clauses point in different directions.`;
                } else if (classification.basis === "no_signal") {
                    basisNote = `No clear appeal direction language found.`;
                } else if (classification.basis === "single_source") {
                    basisNote = `Determined from grounds or prayer clauses.`;
                } else if (classification.basis === "agreement") {
                    basisNote = `Grounds of Appeal and Prayer clauses are in agreement.`;
                }
            } else {
                basisNote = "No case classification details parsed.";
            }

            const summary = data?.grounds_relief_summary || (data?.suggestions && data?.suggestions?.grounds_relief_summary) || null;
            const groundsOfAppeal = summary ? (summary.grounds_of_appeal || []) : [];
            const reliefSought = summary ? (summary.relief_sought || []) : [];

            // Use summarized grounds if available, otherwise raw extracted points
            const effectiveGrounds = groundsOfAppeal.length > 0 ? groundsOfAppeal : ((classification && classification.grounds_points) || []);
            let groundsListHTML = `<span style="opacity: 0.6; font-size: 0.8rem;">No matching grounds statement found.</span>`;
            if (effectiveGrounds.length > 0) {
                groundsListHTML = `<ul style="margin: 4px 0 0 0; padding-left: 16px; display: flex; flex-direction: column; gap: 4px;">
                    ${effectiveGrounds.map(p => `<li style="font-size: 0.82rem; line-height: 1.3; color: var(--text-secondary);">${p}</li>`).join('')}
                </ul>`;
            }

            // Use summarized relief if available, otherwise raw extracted points
            const effectiveRelief = reliefSought.length > 0 ? reliefSought : ((classification && classification.relief_points) || []);
            let reliefListHTML = `<span style="opacity: 0.6; font-size: 0.8rem;">No matching prayer/relief clause found.</span>`;
            if (effectiveRelief.length > 0) {
                reliefListHTML = `<ul style="margin: 4px 0 0 0; padding-left: 16px; display: flex; flex-direction: column; gap: 4px;">
                    ${effectiveRelief.map(p => `<li style="font-size: 0.82rem; line-height: 1.3; color: var(--text-secondary);">${p}</li>`).join('')}
                </ul>`;
            }

            innerHTML = `
                <div style="display: flex; flex-direction: column; gap: 12px;">
                    <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 8px;">
                        <span style="font-size: 0.85rem; font-weight: 700; color: var(--text-primary); text-transform: uppercase;">Enhancement Verdict</span>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span class="badge" style="background: ${label.color}; color: #fff; font-weight: 700; padding: 4px 10px; border-radius: var(--radius-sm); font-size: 0.8rem;">
                                ${label.text}
                            </span>
                            ${verdict !== "not_determinable" ? `<span style="font-size: 0.8rem; color: var(--text-muted); font-weight: 600;">(${confidencePct}%)</span>` : ""}
                        </div>
                    </div>
                    
                    <div style="font-size: 0.78rem; color: var(--text-muted); line-height: 1.4; margin-top: -4px;">
                        ${basisNote}
                    </div>

                    <div style="display: flex; flex-direction: column; gap: 6px; padding: 10px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: var(--radius-sm);">
                        <div style="font-size: 0.82rem; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
                            <i class="fa-solid fa-list-check" style="color: var(--color-primary); font-size: 0.75rem;"></i> Grounds of Appeal
                        </div>
                        <div style="padding-left: 4px;">
                            ${groundsListHTML}
                        </div>
                    </div>

                    <div style="display: flex; flex-direction: column; gap: 6px; padding: 10px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: var(--radius-sm);">
                        <div style="font-size: 0.82rem; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
                            <i class="fa-solid fa-scroll" style="color: var(--color-success); font-size: 0.75rem;"></i> Relief Claimed / Prayer
                        </div>
                        <div style="padding-left: 4px;">
                            ${reliefListHTML}
                        </div>
                    </div>
                </div>
            `;

            // NOTE: High Court Judicial Analysis is intentionally NOT auto-rendered
            // here anymore. It is only ever shown via the dedicated "Check Judicial
            // Analysis" button/panel (checkJudicialAnalysisBtn handler), which itself
            // gates on supporting-document OCR status. Auto-rendering it here — as
            // soon as the main High Court file finished OCR, before any supporting
            // document had been processed — was the bug.


        }


        container.innerHTML = innerHTML;

        // Render Auto-fill button inside the dedicated container below Check Judicial Analysis
        // const autofillContainer = document.getElementById("autofill-button-container");
        // if (autofillContainer) {
        //     autofillContainer.style.display = "block";
        //     autofillContainer.innerHTML = `
        //         <button type="button" id="btn-trigger-autofill" class="btn btn-success" style="width: 100%; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 8px; font-size: 0.82rem; padding: 10px 14px; border-radius: var(--radius-sm); border: none; cursor: pointer; transition: all var(--transition-fast) ease;">
        //             <i class="fa-solid fa-magic"></i> Auto-fill Workstation Form
        //         </button>
        //     `;
        // }



        if (typeof triggerTabNotification === "function") {
            triggerTabNotification("enhancement-check");
        }
    }


    function renderResultsDashboard(res, req) {
        const claimantName = document.getElementById("name")?.value || "N/A";
        const fatherNameVal = document.getElementById("father-name")?.value || "N/A";
        const dateAccidentVal = doaInput.value ? new Date(doaInput.value).toLocaleDateString('en-IN') : "N/A";
        const dateBirthVal = dobInput.value ? new Date(dobInput.value).toLocaleDateString('en-IN') : "N/A";
        const placeAccidentVal = document.getElementById("place-of-accident")?.value || "N/A";
        const caseTypeLabel = res.case_type === "death" ? "Death Claim" : "Injury Claim";

        let parametersHtml = "";
        if (res.case_type === "death") {
            const futureProspectPercent = res.future_prospect_percentage !== undefined ? res.future_prospect_percentage : 0;
            const monthlyIncomeVal = res.monthly_income !== undefined ? res.monthly_income : req.monthly_income;
            const enhancedMonthlyIncomeVal = res.enhanced_monthly_income !== undefined ? res.enhanced_monthly_income : (monthlyIncomeVal * (1 + futureProspectPercent / 100));
            const annualIncomeVal = res.annual_income !== undefined ? res.annual_income : (enhancedMonthlyIncomeVal * 12);

            parametersHtml = `
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Monthly Income</span>
                    <strong>${formatCurrency(monthlyIncomeVal)}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Future Prospects Added</span>
                    <strong>+${futureProspectPercent}%</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Enhanced Monthly Income</span>
                    <strong>${formatCurrency(enhancedMonthlyIncomeVal)}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Annual Income (Enhanced)</span>
                    <strong>${formatCurrency(annualIncomeVal)}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Deduction Applied</span>
                    <strong>${res.deduction_percentage}% (-${formatCurrency(res.deduction_amount)})</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Marital Status</span>
                    <strong>${document.getElementById("marital-status")?.value || "N/A"}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Number of Dependents</span>
                    <strong>${document.getElementById("dependents")?.value || "N/A"}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Deduction Fraction</span>
                    <strong>${res.deduction_label || "N/A"}${res.deduction_is_override ? " (manual override)" : ""}</strong>
                </div>
                ${res.deduction_reason ? `
                <div class="deduction-reason ${res.deduction_is_override ? "deduction-reason--override" : "deduction-reason--auto"}" style="margin: 4px 0 6px;">
                    <span class="deduction-reason-badge">${res.deduction_is_override ? "Manual" : "Recommended"}</span>${res.deduction_reason}
                </div>` : ""}
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Dependency Income</span>
                    <strong>${formatCurrency(res.dependency_income)}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Multiplier Used</span>
                    <strong>${res.multiplier}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Loss of Dependency</span>
                    <strong>${formatCurrency(res.loss_of_dependency)}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Consortium</span>
                    <strong>${formatCurrency(res.consortium)}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Consortium Basis</span>
                    <strong>${document.getElementById("consortium_mode")?.value === "satinder_kaur" ? "Per Legal Heir (Satinder Kaur)" : "Flat"}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Consortium Claimants</span>
                    <strong>${document.getElementById("consortium_claimants")?.value || "N/A"}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Funeral Expenses</span>
                    <strong>${formatCurrency(res.funeral_expenses)}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0;">
                    <span>Loss of Estate</span>
                    <strong>${formatCurrency(res.loss_estate)}</strong>
                </div>
            `;
        } else {
            parametersHtml = `
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Monthly Income</span>
                    <strong>${formatCurrency(req.monthly_income)}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Sarla Verma Multiplier</span>
                    <strong>${res.multiplier}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Permanent Impairment</span>
                    <strong>${req.disability}%</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Medical Expenses</span>
                    <strong>${formatCurrency(res.medical_expenses + res.future_medical_expenses)}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-glass);">
                    <span>Pain & Suffering</span>
                    <strong>${formatCurrency(res.pain_and_suffering)}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0;">
                    <span>Other Allowances (Diet, Attender, Transport, Income Loss)</span>
                    <strong>${formatCurrency(res.transportation + res.special_diet + res.attender_charges + res.loss_of_income)}</strong>
                </div>
            `;
        }

        modalBodyContent.innerHTML = `
            <div class="results-dashboard simplified-dashboard">
                <div class="award-hero" style="text-align: center; margin-bottom: 20px;">
                    <span class="hero-label" style="display: block; font-size: 0.85rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px;">FINAL COMPENSATION</span>
                    <span class="hero-amount" style="display: block; font-size: 2.5rem; font-weight: 800; font-family: 'Outfit', sans-serif; color: var(--color-success); margin: 6px 0; text-shadow: 0 0 20px rgba(52, 211, 153, 0.2);">${formatCurrency(res.final_compensation || res.final_amount)}</span>
                    <span class="hero-tag" style="background: rgba(186, 104, 200, 0.2); color: #e9d5ff; border: 1px solid rgba(186, 104, 200, 0.3); font-size: 0.75rem; padding: 3px 10px; border-radius: 9999px; display: inline-flex; align-items: center; gap: 6px;"><i class="fa-solid fa-gavel"></i> ${caseTypeLabel}</span>
                </div>

                <div class="briefing-container" style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 0.85rem; border: 1px solid var(--border-glass); padding: 16px; border-radius: var(--radius-sm); background: rgba(255,255,255,0.01); margin-bottom: 20px; color: var(--text-primary);">
                    <div><strong>Claimant / Deceased Name:</strong> ${claimantName}</div>
                    <div><strong>Father / Husband Name:</strong> ${fatherNameVal}</div>
                    <div><strong>Date of Birth (Age):</strong> ${dateBirthVal} (${req.age} years)</div>
                    <div><strong>Date of Accident:</strong> ${dateAccidentVal}</div>
                    <div style="grid-column: span 2;"><strong>Place of Accident:</strong> ${placeAccidentVal}</div>
                </div>

                <div class="parameters-summary-box" style="border: 1px solid var(--border-glass); border-radius: var(--radius-sm); background: rgba(255,255,255,0.02); padding: 16px; color: var(--text-primary);">
                    <h4 style="margin-top: 0; margin-bottom: 12px; font-family: 'Outfit', sans-serif; font-size: 0.95rem; border-bottom: 1px solid var(--border-glass); padding-bottom: 6px; color: var(--color-primary); display: flex; align-items: center; gap: 8px;"><i class="fa-solid fa-list-check"></i> Calculation Parameters</h4>
                    <div style="display: flex; flex-direction: column; gap: 8px; font-size: 0.85rem;">
                        ${parametersHtml}
                    </div>
                </div>
            </div>
        `;

        const finalCompEl = document.getElementById("final-compensation");
        if (finalCompEl) {
            finalCompEl.innerText = `₹ ${(res.final_compensation || res.final_amount).toLocaleString("en-IN")}`;
        }
    }

    // Modal controls
    function openModal() { resultsModal.classList.add("open"); }
    function closeModal() { resultsModal.classList.remove("open"); }

    closeModalBtn.addEventListener("click", closeModal);
    dismissModalBtn.addEventListener("click", closeModal);
    window.addEventListener("click", (e) => {
        if (e.target === resultsModal) closeModal();
    });

    document.getElementById("reset-btn").addEventListener("click", () => {
        compensationForm.reset();
        currentCaseSessionId = null;
        if (supportingDocsSection) {
            supportingDocsSection.style.display = "none";
        }
        if (supportingDocsChips) {
            supportingDocsChips.innerHTML = "";
        }
        if (singleDropZone) {
            singleDropZone.classList.remove("compact");
        }
        setCaseDocumentsCollapsed(false);
        setSupportingDocsCollapsed(false);
        updateCaseDocumentsBadge();

        window.lastRawText = "";
        const suggestionDiv = document.getElementById("case-type-suggestion");
        if (suggestionDiv) {
            suggestionDiv.innerHTML = "";
            suggestionDiv.classList.add("hidden-section");
        }

        const autofillContainer = document.getElementById("autofill-button-container");
        if (autofillContainer) {
            autofillContainer.innerHTML = "";
            autofillContainer.style.display = "none";
        }

        // Clear all live calculated dashboard elements back to hyphens
        ["live-calc-annual", "live-calc-future", "live-calc-deduct-pct", "live-calc-deduct-amt", "live-calc-multiplier", "live-calc-dependency", "live-calc-total"].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = "—";
        });

        // Clear AI metadata badges
        document.querySelectorAll(".ai-metadata-badge").forEach(el => el.remove());

        // Reset live OCR timers
        if (ocrTimerInterval) {
            clearInterval(ocrTimerInterval);
            ocrTimerInterval = null;
        }
        ocrSecondsElapsed = 0;

        const headerTimerContainer = document.getElementById("header-ocr-timer-badge");
        const headerElapsedText = document.getElementById("header-ocr-timer-elapsed");
        const statusIcon = document.getElementById("ocr-timer-status-icon");
        const statusText = document.getElementById("ocr-timer-status-text");
        const elapsedText = document.getElementById("ocr-timer-elapsed");

        if (headerElapsedText) {
            headerElapsedText.textContent = "Ready";
        }
        if (headerTimerContainer) {
            headerTimerContainer.style.color = "var(--text-secondary)";
            headerTimerContainer.style.borderColor = "var(--border-glass)";
            headerTimerContainer.style.background = "rgba(15, 23, 42, 0.04)";
        }
        if (statusIcon) {
            statusIcon.innerHTML = `<i class="fa-solid fa-clock" style="color: var(--color-primary);"></i>`;
        }
        if (statusText) {
            statusText.textContent = "Ready for upload";
            statusText.style.color = "var(--text-secondary)";
        }
        if (elapsedText) {
            elapsedText.textContent = "Ready";
            elapsedText.style.color = "var(--text-secondary)";
        }

        sharedFields.classList.remove("show");
        sharedFields.classList.add("hidden-section");

        deathFields.classList.remove("show");
        deathFields.classList.add("hidden-section");

        injuryFields.classList.remove("show");
        injuryFields.classList.add("hidden-section");

        formActionsBar.classList.remove("show-flex");
        formActionsBar.classList.add("hidden-section");

        if (liveMetricsCard) {
            liveMetricsCard.classList.remove("show");
            liveMetricsCard.classList.add("hidden-section");
        }
        if (evaluatorCard) {
            evaluatorCard.classList.remove("show");
            evaluatorCard.classList.add("hidden-section");
        }

        singleUploadSection.classList.remove("hidden-section");
        singleUploadSection.classList.add("show-flex");
        singlePreviewCard.classList.add("hidden-section");
        singlePreviewCard.classList.remove("show");
        singlePreviewContainer.innerHTML = `
            <div class="preview-empty-state" style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 10px; opacity: 0.5;">
                <i class="fa-solid fa-file-pdf" style="font-size: 3rem; color: var(--color-primary)"></i>
                <p style="font-size: 0.8rem; color: var(--text-secondary)">Upload a PDF on the left to see the live document preview here.</p>
            </div>
        `;
        if (singlePreviewFilename) {
            singlePreviewFilename.textContent = "No File Loaded";
        }

        const summaryCard = document.getElementById("legal-ai-summary-card");
        if (summaryCard) {
            summaryCard.classList.add("hidden-section");
            summaryCard.classList.remove("show");
            const summaryBody = document.getElementById("legal-ai-summary-body");
            if (summaryBody) {
                summaryBody.innerHTML = `
                    <div class="empty-summary-state" style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; opacity: 0.5; padding: 20px 0;">
                        <i class="fa-solid fa-gavel" style="font-size: 2.5rem; color: #c084fc;"></i>
                        <p style="font-size: 0.8rem; color: var(--text-secondary); text-align: center; margin: 0;">Upload a PDF to see the structured legal analysis summary and judicial anomaly checklist.</p>
                    </div>
                `;
            }
        }

        const tableCard = document.getElementById("compensation-table-card");
        if (tableCard) {
            tableCard.classList.add("hidden-section");
            tableCard.classList.remove("show");
            const tableBody = document.getElementById("compensation-table-body");
            if (tableBody) {
                tableBody.innerHTML = `
                    <div class="empty-table-state" style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; opacity: 0.5; padding: 20px 0;">
                        <i class="fa-solid fa-table-list" style="font-size: 2.5rem; color: #34d399;"></i>
                        <p style="font-size: 0.8rem; color: var(--text-secondary); text-align: center; margin: 0;">Upload a PDF to view the detailed breakdown of the judicial award heads.</p>
                    </div>
                `;
            }
        }

        if (triggerEvalBtn) triggerEvalBtn.disabled = true;
        currentCalculationAmount = 0;
        // Removed old enhancement card and button references
    });

    // ==========================================================================
    const slideover = document.getElementById("right-slideover");
    const closeSlideover = document.getElementById("close-slideover");
    const aiAssistantTrigger = document.getElementById("ai-assistant-trigger");
    const chatPromptBubble = document.getElementById("chat-prompt-bubble");
    const chatPromptClose = document.getElementById("chat-prompt-close");
    const chatPromptText = document.getElementById("chat-prompt-text");

    // Typewriter effect function for query bubble
    function initTypewriter() {
        if (!chatPromptText) return;
        const message = "Ask your query...";
        let i = 0;
        chatPromptText.textContent = "";
        chatPromptText.classList.add("typing");
        
        function type() {
            if (i < message.length) {
                chatPromptText.textContent += message.charAt(i);
                i++;
                setTimeout(type, 100); // 100ms per character
            } else {
                // Remove cursor blinking after completion
                setTimeout(() => {
                    chatPromptText.classList.remove("typing");
                    chatPromptText.style.borderRight = "none";
                }, 1500);
            }
        }
        
        // Start typing after a short delay (1.2s)
        setTimeout(type, 1200);
    }

    initTypewriter();

    const assistantChatMessages = document.getElementById("assistant-chat-messages");
    const assistantChatInput = document.getElementById("assistant-chat-input");
    const assistantChatSendBtn = document.getElementById("assistant-chat-send-btn");
    const clearAssistantChatBtn = document.getElementById("clear-assistant-chat-btn");
    let assistantChatHistory = [];

    // --- WORKSTATION RIGHT PANE TABS CONTROLLER ---
    const paneTabButtons = document.querySelectorAll(".pane-tab-btn");
    const paneTabContents = document.querySelectorAll(".pane-tab-content");
    const benchmarkingTabDot = document.getElementById("benchmarking-tab-dot");
    const enhancementCheckTabDot = document.getElementById("enhancement-check-tab-dot");

    paneTabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-pane-tab");

            // Switch tabs active styles
            paneTabButtons.forEach(b => {
                if (b === btn) {
                    b.classList.add("active");
                    b.style.background = "rgba(11, 58, 114, 0.06)";
                    b.style.borderColor = "rgba(11, 58, 114, 0.25)";
                    b.style.color = "var(--color-primary)";
                } else {
                    b.classList.remove("active");
                    b.style.background = "transparent";
                    b.style.borderColor = "transparent";
                    b.style.color = "var(--text-secondary)";
                }
            });

            // Toggle tab content display
            paneTabContents.forEach(content => {
                if (content.id === `pane-tab-${targetTab}-content`) {
                    content.classList.add("active");
                    content.classList.remove("hidden");
                } else {
                    content.classList.remove("active");
                    content.classList.add("hidden");
                }
            });

            // Clear dot when tab is clicked
            if (targetTab === "benchmarking" && benchmarkingTabDot) {
                benchmarkingTabDot.classList.add("hidden");
            } else if (targetTab === "enhancement-check" && enhancementCheckTabDot) {
                enhancementCheckTabDot.classList.add("hidden");
            }
        });
    });

    // Helper to get active tab
    function getActiveRightPaneTab() {
        const activeBtn = document.querySelector(".pane-tab-btn.active");
        return activeBtn ? activeBtn.getAttribute("data-pane-tab") : "pdf";
    }

    window.triggerTabNotification = function (tabName) {
        if (getActiveRightPaneTab() !== tabName) {
            if (tabName === "benchmarking" && benchmarkingTabDot) {
                benchmarkingTabDot.classList.remove("hidden");
            } else if (tabName === "enhancement-check" && enhancementCheckTabDot) {
                enhancementCheckTabDot.classList.remove("hidden");
            }
        }
    };

    // --- CHAT READ MODAL ENGINE (BIG BOX VIEWER) ---
    const chatReadModal = document.getElementById("chat-read-modal");
    const chatModalBodyContent = document.getElementById("chat-modal-body-content");
    const closeChatModalBtn = document.getElementById("close-chat-modal-btn");
    const dismissChatModalBtn = document.getElementById("dismiss-chat-modal-btn");

    window.openChatReader = function (htmlContent) {
        if (chatReadModal && chatModalBodyContent) {
            chatModalBodyContent.innerHTML = htmlContent;
            chatReadModal.classList.add("open");
        }
    };

    window.closeChatReader = function () {
        if (chatReadModal) {
            chatReadModal.classList.remove("open");
        }
    };

    if (closeChatModalBtn) closeChatModalBtn.addEventListener("click", closeChatReader);
    if (dismissChatModalBtn) dismissChatModalBtn.addEventListener("click", closeChatReader);

    // Close modal when clicking outside content area
    window.addEventListener("click", (e) => {
        if (e.target === chatReadModal) {
            closeChatReader();
        }
    });

    // Function to attach click listeners to chat texts
    window.bindChatBubbleClick = function (bubbleElement) {
        const textElement = bubbleElement.querySelector(".chat-text");
        if (textElement) {
            textElement.addEventListener("click", () => {
                openChatReader(textElement.innerHTML);
            });
        }
    };

    // Bind existing bubbles on startup
    document.querySelectorAll(".chat-bubble").forEach(bubble => {
        bindChatBubbleClick(bubble);
    });

    // Wide view toggle inside slideover header
    const expandSlideoverBtn = document.getElementById("expand-slideover-btn");
    if (expandSlideoverBtn) {
        expandSlideoverBtn.addEventListener("click", () => {
            if (slideover) {
                slideover.classList.toggle("expanded");
                const icon = expandSlideoverBtn.querySelector("i");
                if (icon) {
                    if (slideover.classList.contains("expanded")) {
                        icon.className = "fa-solid fa-compress";
                        expandSlideoverBtn.title = "Toggle Normal View";
                    } else {
                        icon.className = "fa-solid fa-expand";
                        expandSlideoverBtn.title = "Toggle Wide View";
                    }
                }
            }
        });
    }

    if (aiAssistantTrigger) {
        aiAssistantTrigger.addEventListener("click", () => {
            if (chatPromptBubble) {
                chatPromptBubble.style.opacity = "0";
                chatPromptBubble.style.visibility = "hidden";
                chatPromptBubble.style.pointerEvents = "none";
                chatPromptBubble.style.transform = "translateY(-10px) scale(0.95)";
            }

            if (aiAssistantTrigger.classList.contains("active") && slideover.classList.contains("open")) {
                closeDrawer();
                return;
            }

            aiAssistantTrigger.classList.add("active");
            slideover.classList.add("open");

            // Auto generate CASE BRIEF on open
            generateCaseBrief();
        });
    }

    if (chatPromptClose && chatPromptBubble) {
        chatPromptClose.addEventListener("click", (e) => {
            e.stopPropagation();
            chatPromptBubble.style.opacity = "0";
            chatPromptBubble.style.visibility = "hidden";
            chatPromptBubble.style.pointerEvents = "none";
            chatPromptBubble.style.transform = "translateY(-10px) scale(0.95)";
        });
    }

    function closeDrawer() {
        if (slideover) {
            slideover.classList.remove("open");
            slideover.classList.remove("expanded");
            if (expandSlideoverBtn) {
                const icon = expandSlideoverBtn.querySelector("i");
                if (icon) {
                    icon.className = "fa-solid fa-expand";
                    expandSlideoverBtn.title = "Toggle Wide View";
                }
            }
        }
        if (aiAssistantTrigger) aiAssistantTrigger.classList.remove("active");
    }

    if (closeSlideover) {
        closeSlideover.addEventListener("click", closeDrawer);
    }

    // Generate formatted Case Brief automatically based on workstation inputs
    function generateCaseBrief() {
        const caseType = caseTypeSelect.value || "N/A";
        const caseTypeLabel = caseType === "death" ? "Death Claim" : (caseType === "injury" ? "Injury Claim" : "N/A");

        const claimantName = document.getElementById("name")?.value || "N/A";
        const respondentName = "Insurance Company / Respondent";
        const ageVal = ageInput.value ? `${ageInput.value} years` : "N/A";
        const monthlyIncome = parseFloat(monthlyIncomeInput.value) || 0;
        const incomeVal = monthlyIncome > 0 ? formatCurrency(monthlyIncome) : "N/A";

        const disabilityInput = document.getElementById("disability");
        const disabilityVal = (caseType === "injury" && disabilityInput && disabilityInput.value) ? `${disabilityInput.value}%` : "N/A";

        const awardAmountVal = currentCalculationAmount > 0 ? formatCurrency(currentCalculationAmount) : "N/A";
        const statusVal = currentCalculationAmount > 0 ? "Calculated (Deterministic Math)" : "Awaiting Mathematical Input";

        const occupationVal = "Salaried / Self-Employed";

        const contentEl = document.getElementById("assistant-case-brief-content");
        if (contentEl) {
            contentEl.innerHTML = `
                <table style="width:100%; border-collapse:collapse; font-size:0.8rem; line-height:1.6;">
                    <tr><td style="padding:4px 0; color:var(--text-muted);">Case Type:</td><td style="padding:4px 0; text-align:right; font-weight:600; color:var(--text-primary);">${caseTypeLabel}</td></tr>
                    <tr><td style="padding:4px 0; color:var(--text-muted);">Claimant:</td><td style="padding:4px 0; text-align:right; font-weight:600; color:var(--text-primary);">${claimantName}</td></tr>
                    <tr><td style="padding:4px 0; color:var(--text-muted);">Respondent:</td><td style="padding:4px 0; text-align:right; font-weight:600; color:var(--text-primary);">${respondentName}</td></tr>
                    <tr><td style="padding:4px 0; color:var(--text-muted);">Age:</td><td style="padding:4px 0; text-align:right; font-weight:600; color:var(--text-primary);">${ageVal}</td></tr>
                    <tr><td style="padding:4px 0; color:var(--text-muted);">Occupation:</td><td style="padding:4px 0; text-align:right; font-weight:600; color:var(--text-primary);">${occupationVal}</td></tr>
                    <tr><td style="padding:4px 0; color:var(--text-muted);">Income:</td><td style="padding:4px 0; text-align:right; font-weight:600; color:var(--text-primary);">${incomeVal}</td></tr>
                    <tr><td style="padding:4px 0; color:var(--text-muted);">Disability:</td><td style="padding:4px 0; text-align:right; font-weight:600; color:var(--text-primary);">${disabilityVal}</td></tr>
                    <tr><td style="padding:4px 0; color:var(--text-muted);">Award Amount:</td><td style="padding:4px 0; text-align:right; font-weight:700; color:var(--color-success);">${awardAmountVal}</td></tr>
                    <tr><td style="padding:4px 0; color:var(--text-muted);">Status:</td><td style="padding:4px 0; text-align:right; font-weight:600; color:${currentCalculationAmount > 0 ? '#34d399' : '#f59e0b'};">${statusVal}</td></tr>
                </table>
            `;
        }
    }

    // Bind Suggested Question Pills immediately
    document.querySelectorAll(".suggested-question-pill").forEach(pill => {
        pill.addEventListener("click", () => {
            const questionKey = pill.getAttribute("data-question");
            const displayLabel = pill.getAttribute("data-display") || questionKey;
            if (assistantChatInput) {
                assistantChatInput.value = questionKey;
                handleAssistantChatSend(displayLabel);
            }
        });
    });

    // Side panel chat submission
    if (assistantChatSendBtn) {
        assistantChatSendBtn.addEventListener("click", handleAssistantChatSend);
    }
    if (assistantChatInput) {
        assistantChatInput.addEventListener("keypress", (e) => {
            if (e.key === "Enter") handleAssistantChatSend();
        });
    }
    if (clearAssistantChatBtn) {
        clearAssistantChatBtn.addEventListener("click", () => {
            assistantChatHistory = [];
            assistantChatMessages.innerHTML = `
                <div class="chat-bubble bot">
                    <div class="chat-avatar"><i class="fa-solid fa-robot"></i></div>
                    <div class="chat-text">
                        Hello! I am your AI Legal Assistant. Click questions above to start auditing the workstation state!
                    </div>
                </div>
            `;
        });
    }

    async function handleAssistantChatSend(displayLabel = null) {
        await window.autofillReadyPromise;
        const query = assistantChatInput.value.trim();
        if (!query) return;

        const isJustify = query === "JUSTIFY_COMPENSATION";
        const userDisplayText = displayLabel || query;

        appendAssistantChatBubble(userDisplayText, "user");
        assistantChatInput.value = "";

        const loadingId = appendAssistantChatBubble(`<i class="fa-solid fa-spinner fa-spin"></i> ${isJustify ? "Analysing grounds, facts & compensation heads..." : "Auditing workstation state & searching precedents..."}`, "bot", true);

        try {
            // Retrieve current workstation inputs for full LLM validation context (Phase 8 integration)
            const caseType = caseTypeSelect.value;
            const parsedFields = {
                case_type: caseType,
                name: document.getElementById("name")?.value || "",
                father_name: document.getElementById("father-name")?.value || "",
                age: parseInt(ageInput.value) || 0,
                monthly_income: parseFloat(monthlyIncomeInput.value) || 0,
                disability: parseFloat(document.getElementById("disability")?.value) || 0,
                dependents: parseInt(dependentsInput.value) || 0,
                marital_status: maritalStatusSelect.value || "married",
                award_amount: lastExtractedFields["total_compensation"] || lastExtractedFields["award_amount"] || "",

                // Tribunal per-head figures from PDF (parsed by OCR)
                tribunal_medical: lastExtractedFields["medical_expenses"] || "",
                tribunal_pain_suffering: lastExtractedFields["pain_and_suffering"] || "",
                tribunal_transport: lastExtractedFields["transportation"] || "",
                tribunal_special_diet: lastExtractedFields["special_diet"] || "",
                tribunal_attender: lastExtractedFields["attender_charges"] || "",
                tribunal_loss_of_income: lastExtractedFields["loss_of_income"] || "",
                tribunal_future_medical: lastExtractedFields["future_medical_expenses"] || "",
                tribunal_consortium: lastExtractedFields["consortium"] || "",
                tribunal_funeral: lastExtractedFields["funeral_expenses"] || "",
                tribunal_estate: lastExtractedFields["loss_estate"] || "",
                extracted_age: lastExtractedFields["age"] || "",
                age_source: lastExtractedFields["age_source"] || "",
                extracted_disability: lastExtractedFields["disability"] || "",
                extracted_monthly_income: lastExtractedFields["monthly_income"] || "",
                extracted_dependents: lastExtractedFields["dependents"] || ""
            };

            const calculatorResult = currentCalculationAmount > 0 ? {
                case_type: caseType,
                final_amount: currentCalculationAmount,
                total_compensation: currentCalculationAmount,
                multiplier: currentCalculationBreakdown.multiplier || null,
                annual_income: currentCalculationBreakdown.annual_income || 0,
                future_income_loss: currentCalculationBreakdown.future_income_loss || 0,
                medical_expenses: currentCalculationBreakdown.medical_expenses || 0,
                future_medical_expenses: currentCalculationBreakdown.future_medical_expenses || 0,
                pain_and_suffering: currentCalculationBreakdown.pain_and_suffering || 0,
                transportation: currentCalculationBreakdown.transportation || 0,
                special_diet: currentCalculationBreakdown.special_diet || 0,
                attender_charges: currentCalculationBreakdown.attender_charges || 0,
                loss_of_income: currentCalculationBreakdown.loss_of_income || 0,
                loss_of_dependency: currentCalculationBreakdown.loss_of_dependency || 0,
                consortium: currentCalculationBreakdown.consortium || 0,
                funeral_expenses: currentCalculationBreakdown.funeral_expenses || 0,
                loss_estate: currentCalculationBreakdown.loss_estate || 0,
                deduction_percentage: currentCalculationBreakdown.deduction_percentage || 0,
                future_prospect_percentage: currentCalculationBreakdown.future_prospect_percentage || 0
            } : null;

            // Identify current active PDF filename
            let filename = null;
            if (singlePreviewFilename && singlePreviewFilename.innerHTML) {
                const parts = singlePreviewFilename.innerHTML.split("<span");
                if (parts.length > 0) {
                    filename = parts[0].trim();
                }
            }

            const payload = {
                question: query,
                filename: (filename && filename !== "No File Loaded") ? filename : null,
                ocr_text: currentOcrRawText ? currentOcrRawText.join("\n") : "",
                parsed_fields: parsedFields,
                calculator_result: calculatorResult,
                is_justify: isJustify,
                history: assistantChatHistory.slice(-12),
                case_session_id: currentCaseSessionId
            };

            const response = await fetch("/api/chat/pdf/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error("Assistant API returned error");

            document.getElementById(loadingId).remove();

            // Create a bot chat bubble to append tokens to
            const botBubbleId = appendAssistantChatBubble("", "bot", false);
            const botBubble = document.getElementById(botBubbleId);
            const chatTextDiv = botBubble ? botBubble.querySelector(".chat-text") : null;

            function formatText(text) {
                return text
                    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                    .replace(/\*(.*?)\*/g, '<em>$1</em>')
                    .replace(/\n/g, '<br>');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let accumulatedText = "";
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
                        accumulatedText += token;
                        if (chatTextDiv) {
                            chatTextDiv.innerHTML = formatText(accumulatedText);
                        }
                        assistantChatMessages.scrollTop = assistantChatMessages.scrollHeight;
                    } catch (e) {
                        console.warn("Error parsing stream line:", e);
                    }
                }
            }

            if (buffer.trim()) {
                try {
                    const parsed = JSON.parse(buffer);
                    const token = parsed.message?.content || "";
                    accumulatedText += token;
                    if (chatTextDiv) {
                        chatTextDiv.innerHTML = formatText(accumulatedText);
                    }
                } catch (e) {}
            }

            // Bind click handlers to the newly populated bubble
            if (typeof bindChatBubbleClick === "function" && botBubble) {
                bindChatBubbleClick(botBubble);
            }

            // Append turn to history
            assistantChatHistory.push({ role: "user", content: query });
            assistantChatHistory.push({ role: "assistant", content: accumulatedText });



        } catch (error) {
            console.error("AI Legal Assistant error:", error);
            document.getElementById(loadingId).remove();
            appendAssistantChatBubble("I apologize, but I encountered an error auditing the workstation state. Please ensure the local Ollama service is running.", "bot");
        }
    }

    function appendAssistantChatBubble(text, sender, isLoader = false) {
        const bubble = document.createElement("div");
        const id = `ast_msg_${Date.now()}`;
        bubble.id = id;
        bubble.className = `chat-bubble ${sender}`;

        const avatarHtml = sender === "bot" ? `<i class="fa-solid fa-robot"></i>` : `<i class="fa-solid fa-user-tie"></i>`;

        let formattedText = text;
        if (!isLoader && sender === "bot" && !text.includes("<ul") && !text.includes("<table")) {
            formattedText = text
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/\n/g, '<br>');
        }

        bubble.innerHTML = `
            <div class="chat-avatar">${avatarHtml}</div>
            <div class="chat-text" style="flex: 1; min-width: 0; overflow-wrap: break-word; font-size: 0.85rem; line-height: 1.5;">${formattedText}</div>
        `;

        assistantChatMessages.appendChild(bubble);
        assistantChatMessages.scrollTop = assistantChatMessages.scrollHeight;

        if (!isLoader && typeof bindChatBubbleClick === "function") {
            bindChatBubbleClick(bubble);
        }

        return id;
    }

    // Escape key listener to close drawer
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeDrawer();
        }
    });

    // Explicit Calculate Button Click Handler & Logger
    const calculateBtn = document.getElementById("calculate-btn");
    if (calculateBtn) {
        calculateBtn.addEventListener("click", (e) => {
            compensationForm.dispatchEvent(new Event("submit"));
        });
    }

    if (printBtn) {
        printBtn.addEventListener("click", () => { window.print(); });
    }

    // Keep this list in sync with commonMapping/injuryMapping/deathMapping inside applyAllOcrSuggestions().
    const AUTOFILL_TARGET_FIELD_IDS = [
        "name", "father-name", "date-of-birth", "age", "monthly-income",
        "date-of-accident", "place-of-accident",
        "medical-expenses", "future-medical-expenses", "pain-and-suffering",
        "transportation", "special-diet", "attender-charges", "loss-of-income", "disability",
        "consortium", "funeral-expenses", "loss-estate", "marital-status", "future-type",
        "claimant-relationship-display", "claimant-relationship-type-hidden", "dependents",
        "conspo", "conwif", "conhus", "conpar", "conchil", "conmo", "confath", "conbro", "consis", "conlum",
        "coliti", "misex", "loamiti", "lopmarri", "loexlife", "loveaff", "lossofenjoy"
    ];

    function setAutofillFieldsPending(isPending) {
        AUTOFILL_TARGET_FIELD_IDS.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            if (isPending) {
                el.value = "";
                el.disabled = true;
                el.classList.add("autofill-pending");
            } else {
                el.disabled = false;
                el.classList.remove("autofill-pending");
            }
        });
    }

    // Delegated click handler on autofill-button-container for the Auto-fill button
    const autofillContainer = document.getElementById("autofill-button-container");
    if (autofillContainer) {
        autofillContainer.addEventListener("click", async (e) => {
            const btn = e.target.closest("#btn-trigger-autofill");
            if (btn) {
                e.preventDefault();
                e.stopPropagation();

                const data = window.lastUploadedOcrData;
                if (!data || !data.suggestions) {
                    showToast("No pre-parsed suggestion data available. Please upload a file first.", "warning");
                    return;
                }

                // Show loading spinner on button
                const origHTML = btn.innerHTML;
                btn.disabled = true;
                btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> AI Legal LLM is refining extracted fields...`;
                setAutofillFieldsPending(true);

                try {
                    let success = false;
                    if (currentOcrRawText && currentOcrRawText.length > 0) {
                        success = await runAiRecovery(currentOcrRawText, window.detectedTrack);
                    }
                    if (!success) {
                        applyAllOcrSuggestions(data.suggestions, null, null, null, false, true);
                        showToast("AI refinement unavailable — filled from heuristic OCR extraction only. Please review all fields.", "warning");
                    }
                } catch (err) {
                    console.error("Autofill click handler error:", err);
                    applyAllOcrSuggestions(data.suggestions, null, null, null, false, true);
                    showToast("AI refinement unavailable — filled from heuristic OCR extraction only. Please review all fields.", "warning");
                } finally {
                    setAutofillFieldsPending(false);
                    btn.disabled = false;
                    btn.innerHTML = origHTML;
                }
            }
        });
    }

    // Collapsible sections toggle click listener
    document.querySelectorAll(".toggle-collapse-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const targetId = btn.getAttribute("data-target");
            const target = document.getElementById(targetId);
            if (target) {
                const isHidden = target.style.display === "none" || target.classList.contains("hidden-section");
                if (isHidden) {
                    target.style.display = "grid";
                    target.classList.remove("hidden-section");
                } else {
                    target.style.display = "none";
                    target.classList.add("hidden-section");
                }
            }
        });
    });

    // Global exposure of local math calculator for parity tests
    window.calculateCompensationLocally = calculateCompensationLocally;

    // --- SUPPORTING DOCUMENTS UI & PROCESSING ENGINE ---
    const supportingDocsSection = document.getElementById("supporting-docs-section");
    const addSupportingDocsBtn = document.getElementById("add-supporting-docs-btn");
    const supportingDocsInput = document.getElementById("supporting-docs-input");
    const supportingDocsChips = document.getElementById("supporting-docs-chips");

    if (addSupportingDocsBtn && supportingDocsInput) {
        addSupportingDocsBtn.addEventListener("click", () => {
            setSupportingDocsCollapsed(false);
            supportingDocsInput.click();
        });
    }

    if (supportingDocsInput) {
        supportingDocsInput.addEventListener("change", (e) => {
            if (e.target.files.length > 0) {
                handleSupportingDocsSelect(e.target.files);
            }
        });
    }

    function handleSupportingDocsSelect(files) {
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const file_id = "supp_" + Math.random().toString(36).substring(2, 12);
            renderSupportingDocChip(file, file_id);
        }
        supportingDocsInput.value = ""; // Reset input so same file can be selected again
    }

    function renderSupportingDocChip(file, file_id) {
        const chip = document.createElement("div");
        chip.className = "supporting-doc-chip";
        chip.id = file_id;
        chip.innerHTML = `
            <div class="chip-row chip-row-top">
                <div class="chip-file-info">
                    <i class="fa-solid fa-file-pdf chip-file-icon"></i>
                    <span class="filename" title="${file.name}">${file.name}</span>
                </div>
                <div class="action-container">
                    <span class="status-badge queued">queued</span>
                    <button type="button" class="preview-extraction-btn" title="View extracted text" style="display: none;">
                        <i class="fa-solid fa-eye"></i>
                    </button>
                    <button type="button" class="remove-doc-btn" title="Remove this document">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>
            </div>

            <div class="chip-row chip-row-bottom">
                <select class="doc-type-select">
                    <option value="lower_court">Lower Court Judgment</option>
                    <option value="hospital_record">Medical / Hospital Record</option>
                    <option value="other">Other Supporting Document</option>
                </select>

                <label class="enhance-ocr-label">
                    <input type="checkbox" class="enhance-ocr-checkbox">
                    <span>Enhance OCR</span>
                </label>

                <button type="button" class="upload-btn btn btn-primary btn-small">
                    <i class="fa-solid fa-upload"></i> Upload
                </button>
            </div>
        `;

        if (supportingDocsChips) {
            supportingDocsChips.appendChild(chip);
        }
        setSupportingDocsCollapsed(false);
        updateCaseDocumentsBadge();

        const uploadBtn = chip.querySelector(".upload-btn");
        const docTypeSelect = chip.querySelector(".doc-type-select");
        const enhanceOcrCheckbox = chip.querySelector(".enhance-ocr-checkbox");
        const statusBadge = chip.querySelector(".status-badge");
        const previewBtn = chip.querySelector(".preview-extraction-btn");
        const removeBtn = chip.querySelector(".remove-doc-btn");

        uploadBtn.addEventListener("click", () => {
            docTypeSelect.disabled = true;
            enhanceOcrCheckbox.disabled = true;
            uploadBtn.style.display = "none";
            uploadSupportingDoc(file, file_id, docTypeSelect.value, enhanceOcrCheckbox.checked, statusBadge, previewBtn);
        });

        previewBtn.addEventListener("click", () => {
            const rawText = chip.dataset.rawText ? JSON.parse(chip.dataset.rawText) : [];
            showExtractedTextModal(file.name, rawText);
        });

        removeBtn.addEventListener("click", () => {
            removeSupportingDocChip(chip, file, statusBadge);
        });
    }

    // Removes a wrongly-uploaded supporting document. If it hasn't finished
    // indexing yet, this simply drops it from the UI. If it already finished
    // ("done"), the person is asked to confirm since it also needs to be
    // deleted from the backend's Qdrant index so it stops influencing the
    // judicial analysis / autofill.
    async function removeSupportingDocChip(chip, file, statusBadge) {
        const currentStatus = statusBadge ? statusBadge.textContent.trim().toLowerCase() : "";
        const isIndexed = currentStatus === "done";
        const isProcessing = currentStatus === "processing" || (currentStatus && !["queued", "failed", "done", ""].includes(currentStatus));

        if (isIndexed) {
            const confirmed = window.confirm(`Remove "${file.name}" from this case? It will also be removed from the processed documents used for judicial analysis.`);
            if (!confirmed) return;
        } else if (isProcessing) {
            const confirmed = window.confirm(`"${file.name}" is still being processed. Remove it anyway?`);
            if (!confirmed) return;
        }

        chip.style.opacity = "0.5";
        chip.style.pointerEvents = "none";

        if (isIndexed || isProcessing) {
            try {
                await fetch(`/api/qdrant/document/${encodeURIComponent(file.name)}`, { method: "DELETE" });
            } catch (err) {
                console.error("Failed to remove supporting document from index:", err);
            }
            judicialAnalysisCache.clear();
        }

        chip.remove();
        updateCaseDocumentsBadge();
        showToast(`Removed "${file.name}" from case documents.`, "success");
    }

    function showExtractedTextModal(filename, lines) {
        let overlay = document.getElementById("extraction-preview-overlay");
        if (overlay) overlay.remove();

        overlay = document.createElement("div");
        overlay.id = "extraction-preview-overlay";
        overlay.style.cssText = `
            position: fixed; inset: 0; background: rgba(0,0,0,0.6);
            display: flex; align-items: center; justify-content: center;
            z-index: 10000; padding: 24px;
        `;

        const card = document.createElement("div");
        card.style.cssText = `
            background: var(--bg-panel, #1e293b); border: 1px solid var(--border-glass, rgba(255,255,255,0.08));
            border-radius: var(--radius-sm, 8px); width: 100%; max-width: 720px; max-height: 80vh;
            display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        `;

        const bodyText = (lines && lines.length > 0)
            ? lines.join("\n")
            : "No text could be extracted from this document.";

        card.innerHTML = `
            <div style="padding: 14px 18px; border-bottom: 1px solid var(--border-color, rgba(255,255,255,0.08)); display: flex; align-items: center; justify-content: space-between; gap: 12px;">
                <h3 style="margin: 0; font-size: 0.95rem; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    <i class="fa-solid fa-file-lines" style="color: var(--color-primary); margin-right: 8px;"></i>${filename}
                </h3>
                <button type="button" id="extraction-preview-close" style="background: transparent; border: none; color: var(--text-secondary); font-size: 1.1rem; cursor: pointer; line-height: 1;">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
            <div style="padding: 16px 18px; overflow-y: auto; flex: 1;">
                <pre style="white-space: pre-wrap; word-break: break-word; font-family: 'Inter', sans-serif; font-size: 0.85rem; line-height: 1.6; color: var(--text-secondary); margin: 0;"></pre>
            </div>
        `;
        card.querySelector("pre").textContent = bodyText;

        overlay.appendChild(card);
        document.body.appendChild(overlay);

        const closeModal = () => overlay.remove();
        overlay.querySelector("#extraction-preview-close").addEventListener("click", closeModal);
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) closeModal();
        });
    }

    // --- CHECK JUDICIAL ANALYSIS (on-demand, gated on supporting-doc status) ---
    const checkJudicialAnalysisBtn = document.getElementById("check-judicial-analysis-btn");
    const judicialAnalysisResult = document.getElementById("judicial-analysis-result");

    // In-memory cache of generated judicial-analysis reports, keyed per document
    // (case session + OCR text). This means: once a report has been generated
    // for the currently loaded document, clicking "Check Judicial Analysis"
    // again simply reopens the same cached report in the modal instead of
    // calling the backend/LLM again -- so the report never changes between
    // clicks for the same document.
    const judicialAnalysisCache = new Map();

    function getJudicialAnalysisCacheKey() {
        const sessionPart = currentCaseSessionId || "no-session";
        const trackPart = window.detectedTrack || "high_court";
        const caseTypePart = caseTypeSelect ? caseTypeSelect.value : "death";
        // Cheap content fingerprint so a re-upload / different document under
        // the same session doesn't reuse a stale cached report.
        const textPart = (currentOcrRawText || []).join("\n").length + ":" + (currentOcrRawText || []).length;
        return `${sessionPart}|${trackPart}|${caseTypePart}|${textPart}`;
    }

    function renderJudicialProcessingState(message) {
        if (!judicialAnalysisResult) return;
        judicialAnalysisResult.dataset.state = "processing";
        judicialAnalysisResult.style.display = "block";
        judicialAnalysisResult.innerHTML = `
            <div style="padding: 14px; background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.25); border-radius: var(--radius-sm); display: flex; align-items: center; gap: 10px; font-size: 0.85rem; color: var(--text-secondary);">
                <i class="fa-solid fa-spinner fa-spin" style="color: var(--color-primary);"></i>
                ${message}
            </div>
        `;
    }

    function renderJudicialErrorState(message) {
        if (!judicialAnalysisResult) return;
        judicialAnalysisResult.dataset.state = "error";
        judicialAnalysisResult.style.display = "block";
        judicialAnalysisResult.innerHTML = `
            <div style="padding: 14px; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); border-radius: var(--radius-sm); font-size: 0.85rem; color: #f87171;">
                <i class="fa-solid fa-triangle-exclamation"></i> ${message}
            </div>
        `;
    }

    function buildJudicialAnalysisBodyHTML(finalJudicial) {
        const issueWise = finalJudicial.issue_wise_view || [];
        const finalPoints = finalJudicial.final_summary_points || [];
        const probableOutcome = finalJudicial.probable_outcome || "not_determinable";
        const summarySource = finalJudicial.summary_source || "llm_summary";
        const discrepancies = finalJudicial.factual_discrepancies || [];

        let outcomeBadgeColor = "#6c757d";
        let outcomeLabel = "Not Determinable";
        if (probableOutcome === "enhancement") { outcomeBadgeColor = "#22c55e"; outcomeLabel = "Enhancement Likely"; }
        else if (probableOutcome === "reduction") { outcomeBadgeColor = "#eab308"; outcomeLabel = "Reduction Likely"; }
        else if (probableOutcome === "exoneration") { outcomeBadgeColor = "#a855f7"; outcomeLabel = "Exoneration / Set Aside"; }
        else if (probableOutcome === "upheld") { outcomeBadgeColor = "#3b82f6"; outcomeLabel = "Award Upheld"; }

        let degradationNotice = "";
        if (summarySource === "insufficient_input" || summarySource === "fallback") {
            const msg = finalPoints.length > 0 ? finalPoints[0] : "Limited automated analysis -- trial court section not fully detected.";
            degradationNotice = `
                <div style="padding: 8px 12px; background: rgba(234,179,8,0.1); border: 1px solid rgba(234,179,8,0.3); border-radius: var(--radius-sm); font-size: 0.78rem; color: #eab308; margin-top: 4px; display: flex; align-items: center; gap: 8px;">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <span>${msg}</span>
                </div>
            `;
        }

        let issueCardsHTML = "";
        if (issueWise.length > 0) {
            issueCardsHTML = issueWise.map((item, idx) => `
                <div style="padding: 10px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: var(--radius-sm); display: flex; flex-direction: column; gap: 6px;">
                    <div style="font-size: 0.82rem; font-weight: 700; color: var(--color-primary); display: flex; align-items: center; gap: 6px;">
                        <i class="fa-solid fa-gavel" style="font-size: 0.75rem;"></i> Issue ${idx + 1}: ${item.issue || 'Point for Determination'}
                    </div>
                    ${item.trial_court_finding ? `
                        <div style="font-size: 0.78rem; color: var(--text-secondary); background: rgba(255,255,255,0.02); padding: 6px 8px; border-radius: 4px; border-left: 3px solid var(--color-primary);">
                            <strong style="color: var(--text-primary);">Trial Court Finding:</strong> ${item.trial_court_finding}
                        </div>
                    ` : ''}
                    ${item.hc_ground_challenge ? `
                        <div style="font-size: 0.78rem; color: var(--text-secondary); background: rgba(255,255,255,0.02); padding: 6px 8px; border-radius: 4px; border-left: 3px solid #eab308;">
                            <strong style="color: var(--text-primary);">HC Challenge:</strong> ${item.hc_ground_challenge}
                        </div>
                    ` : ''}
                    ${item.likely_judicial_view ? `
                        <div style="font-size: 0.78rem; color: var(--text-secondary); background: rgba(34,197,94,0.05); padding: 6px 8px; border-radius: 4px; border-left: 3px solid #22c55e;">
                            <strong style="color: #22c55e;">Likely Judicial View:</strong> ${item.likely_judicial_view}
                        </div>
                    ` : ''}
                </div>
            `).join('');
        }

        let discrepanciesHTML = "";
        if (discrepancies.length > 0) {
            discrepanciesHTML = `
                <div style="display: flex; flex-direction: column; gap: 6px; padding: 10px; background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: var(--radius-sm); margin-top: 4px;">
                    <div style="font-size: 0.82rem; font-weight: 700; color: #f87171; display: flex; align-items: center; gap: 6px;">
                        <i class="fa-solid fa-triangle-exclamation"></i> Factual Discrepancies &amp; Missing Claims (vs. Trial Court)
                    </div>
                    <ul style="margin: 4px 0 0 0; padding-left: 16px; display: flex; flex-direction: column; gap: 6px;">
                        ${discrepancies.map(d => `
                            <li style="font-size: 0.78rem; line-height: 1.3; color: var(--text-secondary);">
                                <strong style="color: var(--text-primary);">${d.claim}</strong>
                                <span style="display: block; font-size: 0.72rem; color: #ef4444; margin-top: 1px;">
                                    ${d.note || 'Claim omitted or uncompensated in trial court findings.'}
                                </span>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            `;
        }

        let finalBulletsHTML = "";
        if (finalPoints.length > 0 && summarySource === "llm_summary") {
            finalBulletsHTML = `
                <ul style="margin: 4px 0 0 0; padding-left: 16px; display: flex; flex-direction: column; gap: 4px;">
                    ${finalPoints.map(p => `<li style="font-size: 0.82rem; line-height: 1.3; color: var(--text-secondary);">${p}</li>`).join('')}
                </ul>
            `;
        }

        return `
            <div style="display: flex; flex-direction: column; gap: 10px;">
                <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 8px;">
                    <span style="font-size: 0.9rem; font-weight: 700; color: var(--text-primary); text-transform: uppercase; display: inline-flex; align-items: center; gap: 8px;">
                        <i class="fa-solid fa-scale-balanced" style="color: var(--color-primary);"></i> High Court Judicial Analysis
                    </span>
                    <span class="badge" style="background: ${outcomeBadgeColor}; color: #fff; font-weight: 700; padding: 3px 8px; border-radius: var(--radius-sm); font-size: 0.75rem;">
                        ${outcomeLabel}
                    </span>
                </div>
                ${degradationNotice}
                ${issueCardsHTML ? `<div style="display: flex; flex-direction: column; gap: 8px;">${issueCardsHTML}</div>` : ''}
                ${discrepanciesHTML}
                ${finalBulletsHTML ? `
                    <div style="display: flex; flex-direction: column; gap: 6px; padding: 8px; background: rgba(255,255,255,0.01); border-radius: 4px;">
                        <div style="font-size: 0.8rem; font-weight: 700; color: var(--text-primary);">Synthesized Judicial Summary</div>
                        ${finalBulletsHTML}
                    </div>
                ` : ''}
            </div>
        `;
    }

    // Renders the report inside a full modal "window" overlay, following the
    // same visual pattern as showExtractedTextModal, so the entire
    // comparison report is visible at once rather than cramped into the
    // small inline panel.
    function showJudicialAnalysisModal(finalJudicial, fromCache) {
        let overlay = document.getElementById("judicial-analysis-overlay");
        if (overlay) overlay.remove();

        overlay = document.createElement("div");
        overlay.id = "judicial-analysis-overlay";
        overlay.style.cssText = `
            position: fixed; inset: 0; background: rgba(0,0,0,0.6);
            display: flex; align-items: center; justify-content: center;
            z-index: 10000; padding: 24px;
        `;

        const card = document.createElement("div");
        card.style.cssText = `
            background: var(--bg-panel, #1e293b); border: 1px solid var(--border-glass, rgba(255,255,255,0.08));
            border-radius: var(--radius-sm, 8px); width: 100%; max-width: 820px; max-height: 85vh;
            display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        `;

        card.innerHTML = `
            <div style="padding: 14px 18px; border-bottom: 1px solid var(--border-color, rgba(255,255,255,0.08)); display: flex; align-items: center; justify-content: space-between; gap: 12px;">
                <h3 style="margin: 0; font-size: 0.95rem; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                    <i class="fa-solid fa-scale-balanced" style="color: var(--color-primary);"></i> Judicial Analysis &amp; Summary Comparison Report
                    ${fromCache ? `<span style="font-size: 0.7rem; font-weight: 600; color: var(--text-secondary); background: rgba(255,255,255,0.06); padding: 2px 8px; border-radius: 999px;"><i class="fa-solid fa-clock-rotate-left"></i> Cached</span>` : ''}
                </h3>
                <div style="display: flex; align-items: center; gap: 10px; flex-shrink: 0;">
                    <button type="button" id="judicial-analysis-regenerate" title="Regenerate (bypass cache)" style="background: transparent; border: 1px solid var(--border-color); color: var(--text-secondary); font-size: 0.75rem; padding: 4px 10px; border-radius: 6px; cursor: pointer;">
                        <i class="fa-solid fa-rotate"></i> Regenerate
                    </button>
                    <button type="button" id="judicial-analysis-close" style="background: transparent; border: none; color: var(--text-secondary); font-size: 1.1rem; cursor: pointer; line-height: 1;">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>
            </div>
            <div style="padding: 16px 18px; overflow-y: auto; flex: 1;">
                ${buildJudicialAnalysisBodyHTML(finalJudicial)}
            </div>
        `;

        overlay.appendChild(card);
        document.body.appendChild(overlay);

        const closeModal = () => overlay.remove();
        overlay.querySelector("#judicial-analysis-close").addEventListener("click", closeModal);
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) closeModal();
        });
        overlay.querySelector("#judicial-analysis-regenerate").addEventListener("click", () => {
            closeModal();
            runJudicialAnalysis({ forceRefresh: true });
        });
    }

    async function runJudicialAnalysis({ forceRefresh = false } = {}) {
        if (!currentOcrRawText || currentOcrRawText.length === 0) {
            showToast("Please upload and OCR the High Court case file first.", "warning");
            return;
        }

        // Gate: if any supporting-doc chip exists but hasn't finished
        // OCR/indexing yet, show "Processing" instead of running the
        // comparison against incomplete/missing supporting-doc text.
        const chips = supportingDocsChips ? Array.from(supportingDocsChips.querySelectorAll(".supporting-doc-chip")) : [];
        const pendingChip = chips.find(chip => {
            const badge = chip.querySelector(".status-badge");
            const status = badge ? badge.className : "";
            return !status.includes("done") && !status.includes("failed");
        });

        if (pendingChip) {
            renderJudicialProcessingState("Processing the file&hellip; Judicial Analysis will be available once the supporting document finishes OCR.");
            return;
        }

        const cacheKey = getJudicialAnalysisCacheKey();

        // Cache hit: reopen the exact same report immediately, no backend call.
        if (!forceRefresh && judicialAnalysisCache.has(cacheKey)) {
            if (judicialAnalysisResult) {
                judicialAnalysisResult.dataset.state = "done";
                judicialAnalysisResult.style.display = "none"; // full report lives in the modal
            }
            showJudicialAnalysisModal(judicialAnalysisCache.get(cacheKey), true);
            return;
        }

        checkJudicialAnalysisBtn.disabled = true;
        const origHTML = checkJudicialAnalysisBtn.innerHTML;
        checkJudicialAnalysisBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Generating Judicial Analysis...`;
        renderJudicialProcessingState("Processing the file&hellip;");

        try {
            const caseType = caseTypeSelect ? caseTypeSelect.value : "death";
            const response = await fetch("/api/ocr/refresh-judicial-summary", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    raw_text: currentOcrRawText,
                    track: window.detectedTrack || "high_court",
                    case_session_id: currentCaseSessionId,
                    case_type: caseType,
                    force_refresh: forceRefresh
                })
            });

            if (!response.ok) throw new Error("Judicial analysis request failed");
            const data = await response.json();

            if (data.success && data.final_judicial_summary) {
                // Cache client-side too, so a page-local re-click never
                // re-fetches, and mark the small inline panel "done" (the
                // full report itself opens in the modal window).
                judicialAnalysisCache.set(cacheKey, data.final_judicial_summary);
                if (judicialAnalysisResult) {
                    judicialAnalysisResult.dataset.state = "done";
                    judicialAnalysisResult.style.display = "none";
                }
                showJudicialAnalysisModal(data.final_judicial_summary, !!data.cached);
            } else {
                renderJudicialErrorState("Failed to generate Judicial Analysis. Please try again.");
            }
        } catch (err) {
            console.error("Judicial analysis error:", err);
            renderJudicialErrorState(`Failed to generate Judicial Analysis: ${err.message}`);
        } finally {
            checkJudicialAnalysisBtn.disabled = false;
            checkJudicialAnalysisBtn.innerHTML = origHTML;
        }
    }

    if (checkJudicialAnalysisBtn) {
        checkJudicialAnalysisBtn.addEventListener("click", () => runJudicialAnalysis({ forceRefresh: false }));
    }

    async function uploadSupportingDoc(file, file_id, doc_type, enhance_ocr, statusBadge, previewBtn) {
        statusBadge.textContent = "processing";
        statusBadge.className = "status-badge processing";

        const formData = new FormData();
        formData.append("file", file);
        formData.append("doc_type", doc_type);
        formData.append("case_session_id", ensureCaseSessionId());
        formData.append("enhance_ocr", enhance_ocr);

        try {
            const response = await fetch("/api/ocr/process-supporting-doc", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                throw new Error("Supporting document process initiation failed.");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop();

                for (const line of lines) {
                    const cleanLine = line.trim();
                    if (!cleanLine.startsWith("data: ")) continue;

                    const payload = cleanLine.slice(6);
                    const data = JSON.parse(payload);

                    if (data.message) {
                        statusBadge.textContent = data.message;
                    }

                    if (data.status === "done") {
                        if (data.success) {
                            statusBadge.textContent = "done";
                            statusBadge.className = "status-badge done";
                            showToast(`Supporting document "${file.name}" successfully indexed!`, "success");

                            if (previewBtn) {
                                const chipEl = statusBadge.closest(".supporting-doc-chip");
                                if (chipEl) {
                                    chipEl.dataset.rawText = JSON.stringify(data.raw_text || []);
                                }
                                previewBtn.style.display = "inline-flex";
                            }

                            // A new (or changed) supporting document just finished indexing --
                            // any previously cached judicial-analysis report is now stale, since
                            // it was generated without this document's content. Invalidate the
                            // client-side cache so the next click is forced to hit the backend
                            // (which will itself only skip regeneration if its OWN cache key --
                            // which DOES include supporting-doc text -- still matches).
                            judicialAnalysisCache.clear();

                            // If the user already clicked "Check Judicial Analysis" and it's sitting
                            // in the "Processing the file..." state waiting on this document, auto
                            // re-run the check now that OCR just finished.
                            if (checkJudicialAnalysisBtn && judicialAnalysisResult &&
                                judicialAnalysisResult.dataset.state === "processing") {
                                checkJudicialAnalysisBtn.click();
                            }
                            updateCaseDocumentsBadge();
                        } else {
                            statusBadge.textContent = "failed";
                            statusBadge.className = "status-badge failed";
                            showToast(`Failed to process "${file.name}": ${data.message || "Unknown error"}`, "error");
                        }
                    } else if (data.status === "failed") {
                        statusBadge.textContent = "failed";
                        statusBadge.className = "status-badge failed";
                        showToast(`Failed to process "${file.name}": ${data.message || "Unknown error"}`, "error");
                    }
                }
            }
        } catch (err) {
            console.error("Supporting doc upload failed:", err);
            statusBadge.textContent = "failed";
            statusBadge.className = "status-badge failed";
            showToast(`Failed to process "${file.name}": ${err.message}`, "error");
        }
    }

    // PDF Annotation Canvas & Drawing tools
    const annotationCanvas = document.getElementById("pdf-annotation-canvas");
    const pencilTrigger = document.getElementById("pencil-tool-trigger");
    const pencilMenu = document.getElementById("pencil-options-menu");
    const btnPencil = document.getElementById("pencil-btn-pencil");
    const btnMarker = document.getElementById("pencil-btn-marker");
    const btnEraser = document.getElementById("pencil-btn-eraser");
    const btnClear = document.getElementById("pencil-btn-clear");
    const btnNotes = document.getElementById("pencil-btn-notes");
    const btnUndo = document.getElementById("pencil-btn-undo");

    // Short Notes Widget Elements
    const notesContainer = document.getElementById("pdf-notes-container");
    const notesTextarea = document.getElementById("notes-textarea");
    const notesCloseBtn = document.getElementById("notes-close-btn");
    const notesEraseBtn = document.getElementById("notes-erase-btn");

    let isDrawing = false;
    let lastX = 0;
    let lastY = 0;
    let activeTool = "none"; // none, pencil, marker, eraser
    let ctx = null;

    let drawingColor = "#ef4444"; // default drawing color
    let drawingSize = 2.5; // default thin brush size
    let drawingHistory = []; // undo history stack

    if (annotationCanvas) {
        ctx = annotationCanvas.getContext("2d");
    }

    function initCanvasSize() {
        if (!annotationCanvas || !ctx) return;
        const currentWidth = annotationCanvas.clientWidth;
        const currentHeight = annotationCanvas.clientHeight;
        
        // Only set canvas dimensions if they changed, since setting them clears the context
        if (annotationCanvas.width !== currentWidth || annotationCanvas.height !== currentHeight) {
            // Backup current drawings
            const tempCanvas = document.createElement("canvas");
            tempCanvas.width = annotationCanvas.width;
            tempCanvas.height = annotationCanvas.height;
            const tempCtx = tempCanvas.getContext("2d");
            tempCtx.drawImage(annotationCanvas, 0, 0);

            annotationCanvas.width = currentWidth;
            annotationCanvas.height = currentHeight;
            
            // Restore drawings
            ctx.drawImage(tempCanvas, 0, 0);
        }
    }

    // Initialize size on window resize if canvas is active
    window.addEventListener("resize", () => {
        if (activeTool !== "none") {
            initCanvasSize();
        }
    });

    if (pencilTrigger && pencilMenu) {
        pencilTrigger.addEventListener("click", (e) => {
            e.stopPropagation();
            const isMenuOpen = pencilMenu.style.display === "flex";
            pencilMenu.style.display = isMenuOpen ? "none" : "flex";
        });

        // Close menu when clicking outside
        document.addEventListener("click", () => {
            pencilMenu.style.display = "none";
        });

        pencilMenu.addEventListener("click", (e) => {
            e.stopPropagation();
        });
    }

    function selectTool(tool) {
        activeTool = tool;
        if (!annotationCanvas || !ctx) return;

        // Reset highlight states
        [btnPencil, btnMarker, btnEraser].forEach(btn => {
            if (btn) btn.style.background = "transparent";
        });

        if (tool === "none") {
            annotationCanvas.style.display = "none";
            pencilTrigger.style.background = "#eab308";
            pencilTrigger.classList.remove("active");
        } else {
            annotationCanvas.style.display = "block";
            initCanvasSize();
            pencilTrigger.style.background = "#ca8a04";
            pencilTrigger.classList.add("active");
            
            if (tool === "pencil") {
                if (btnPencil) btnPencil.style.background = "rgba(15, 23, 42, 0.08)";
            } else if (tool === "marker") {
                if (btnMarker) btnMarker.style.background = "rgba(15, 23, 42, 0.08)";
            } else if (tool === "eraser") {
                if (btnEraser) btnEraser.style.background = "rgba(15, 23, 42, 0.08)";
            }
        }
    }

    if (btnPencil) {
        btnPencil.addEventListener("click", () => {
            selectTool(activeTool === "pencil" ? "none" : "pencil");
            pencilMenu.style.display = "none";
        });
    }

    if (btnMarker) {
        btnMarker.addEventListener("click", () => {
            selectTool(activeTool === "marker" ? "none" : "marker");
            pencilMenu.style.display = "none";
        });
    }

    if (btnEraser) {
        btnEraser.addEventListener("click", () => {
            selectTool(activeTool === "eraser" ? "none" : "eraser");
            pencilMenu.style.display = "none";
        });
    }

    if (btnClear) {
        btnClear.addEventListener("click", () => {
            if (ctx && annotationCanvas) {
                saveDrawingState();
                ctx.clearRect(0, 0, annotationCanvas.width, annotationCanvas.height);
                showToast("Annotations cleared", "info");
            }
            pencilMenu.style.display = "none";
        });
    }

    // Brush Settings: Color dots selection listener
    const colorDots = document.querySelectorAll("#pencil-colors .color-dot");
    colorDots.forEach(dot => {
        dot.addEventListener("click", (e) => {
            colorDots.forEach(d => d.classList.remove("active"));
            dot.classList.add("active");
            drawingColor = dot.getAttribute("data-color");
            e.stopPropagation();
        });
    });

    // Brush Settings: Size options selection listener
    const sizeBtns = document.querySelectorAll("#pencil-sizes .size-btn");
    sizeBtns.forEach(btn => {
        btn.addEventListener("click", (e) => {
            sizeBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            drawingSize = parseFloat(btn.getAttribute("data-size"));
            e.stopPropagation();
        });
    });

    // Undo drawing feature helper
    function saveDrawingState() {
        if (!annotationCanvas || !ctx) return;
        drawingHistory.push(annotationCanvas.toDataURL());
        if (drawingHistory.length > 30) {
            drawingHistory.shift(); // limit history buffer
        }
    }

    if (btnUndo) {
        btnUndo.addEventListener("click", () => {
            if (drawingHistory.length > 0) {
                const lastState = drawingHistory.pop();
                const img = new Image();
                img.onload = () => {
                    ctx.clearRect(0, 0, annotationCanvas.width, annotationCanvas.height);
                    ctx.drawImage(img, 0, 0);
                };
                img.src = lastState;
                showToast("Undo applied", "info");
            } else {
                showToast("No drawing actions to undo", "warning");
            }
            pencilMenu.style.display = "none";
        });
    }

    // Short Notes: Toggle container visibility
    if (btnNotes && notesContainer) {
        btnNotes.addEventListener("click", () => {
            const isVisible = notesContainer.style.display === "flex";
            notesContainer.style.display = isVisible ? "none" : "flex";
            pencilMenu.style.display = "none";
            if (!isVisible && window.currentPdfName) {
                loadPdfNotes(window.currentPdfName);
            }
        });
    }

    // Short Notes caching helper functions
    window.loadPdfNotes = function(filename) {
        if (!notesTextarea) return;
        const key = "mact_pdf_notes_" + filename;
        const savedNotes = localStorage.getItem(key);
        if (savedNotes) {
            notesTextarea.value = savedNotes;
            updateNotesSaveStatus(true);
        } else {
            notesTextarea.value = "";
            updateNotesSaveStatus(false, "No notes saved");
        }
    };

    function savePdfNotes() {
        if (!notesTextarea) return;
        const filename = window.currentPdfName || "default";
        const key = "mact_pdf_notes_" + filename;
        const val = notesTextarea.value;
        if (val.trim()) {
            localStorage.setItem(key, val);
            updateNotesSaveStatus(true);
        } else {
            localStorage.removeItem(key);
            updateNotesSaveStatus(false, "Empty");
        }
    }

    function updateNotesSaveStatus(saved, customMsg) {
        const statusSpan = document.getElementById("notes-save-status");
        if (!statusSpan) return;
        if (saved) {
            statusSpan.innerHTML = `<i class="fa-solid fa-circle-check" style="color: #10b981;"></i> Saved to cache`;
        } else {
            statusSpan.innerHTML = customMsg ? `<i class="fa-solid fa-info-circle"></i> ${customMsg}` : `<i class="fa-solid fa-circle-xmark"></i> Not saved`;
        }
    }

    // Bind event listeners for notes widget
    if (notesTextarea) {
        notesTextarea.addEventListener("input", savePdfNotes);
    }

    if (notesCloseBtn && notesContainer) {
        notesCloseBtn.addEventListener("click", () => {
            notesContainer.style.display = "none";
        });
    }

    if (notesEraseBtn) {
        notesEraseBtn.addEventListener("click", () => {
            if (confirm("Are you sure you want to completely erase these notes?")) {
                if (notesTextarea) {
                    notesTextarea.value = "";
                    const filename = window.currentPdfName || "default";
                    const key = "mact_pdf_notes_" + filename;
                    localStorage.removeItem(key);
                    updateNotesSaveStatus(false, "Erased");
                    showToast("Notes erased completely", "info");
                }
            }
        });
    }

    // Canvas drawing mouse & touch listeners
    if (annotationCanvas && ctx) {
        annotationCanvas.addEventListener("mousedown", (e) => {
            if (activeTool === "none") return;
            saveDrawingState();
            isDrawing = true;
            const rect = annotationCanvas.getBoundingClientRect();
            lastX = e.clientX - rect.left;
            lastY = e.clientY - rect.top;
        });

        annotationCanvas.addEventListener("mousemove", (e) => {
            if (!isDrawing || activeTool === "none") return;
            const rect = annotationCanvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(x, y);

            if (activeTool === "pencil") {
                ctx.strokeStyle = drawingColor;
                ctx.lineWidth = drawingSize;
                ctx.globalAlpha = 1.0;
                ctx.globalCompositeOperation = "source-over";
                ctx.lineCap = "round";
                ctx.lineJoin = "round";
            } else if (activeTool === "marker") {
                ctx.strokeStyle = drawingColor;
                ctx.lineWidth = 16;
                ctx.globalAlpha = 0.40;
                ctx.globalCompositeOperation = "source-over";
                ctx.lineCap = "square";
                ctx.lineJoin = "miter";
            } else if (activeTool === "eraser") {
                ctx.strokeStyle = "rgba(0,0,0,1)";
                ctx.lineWidth = 24;
                ctx.globalAlpha = 1.0;
                ctx.globalCompositeOperation = "destination-out"; // precision erase
                ctx.lineCap = "round";
                ctx.lineJoin = "round";
            }

            ctx.stroke();
            lastX = x;
            lastY = y;
        });

        annotationCanvas.addEventListener("mouseup", () => { isDrawing = false; });
        annotationCanvas.addEventListener("mouseout", () => { isDrawing = false; });

        // Touch event support for tablets
        annotationCanvas.addEventListener("touchstart", (e) => {
            if (activeTool === "none" || e.touches.length === 0) return;
            saveDrawingState();
            isDrawing = true;
            const rect = annotationCanvas.getBoundingClientRect();
            lastX = e.touches[0].clientX - rect.left;
            lastY = e.touches[0].clientY - rect.top;
            e.preventDefault();
        });

        annotationCanvas.addEventListener("touchmove", (e) => {
            if (!isDrawing || activeTool === "none" || e.touches.length === 0) return;
            const rect = annotationCanvas.getBoundingClientRect();
            const x = e.touches[0].clientX - rect.left;
            const y = e.touches[0].clientY - rect.top;

            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(x, y);

            if (activeTool === "pencil") {
                ctx.strokeStyle = drawingColor;
                ctx.lineWidth = drawingSize;
                ctx.globalAlpha = 1.0;
                ctx.globalCompositeOperation = "source-over";
                ctx.lineCap = "round";
                ctx.lineJoin = "round";
            } else if (activeTool === "marker") {
                ctx.strokeStyle = drawingColor;
                ctx.lineWidth = 16;
                ctx.globalAlpha = 0.40;
                ctx.globalCompositeOperation = "source-over";
                ctx.lineCap = "square";
                ctx.lineJoin = "miter";
            } else if (activeTool === "eraser") {
                ctx.strokeStyle = "rgba(0,0,0,1)";
                ctx.lineWidth = 24;
                ctx.globalAlpha = 1.0;
                ctx.globalCompositeOperation = "destination-out";
                ctx.lineCap = "round";
                ctx.lineJoin = "round";
            }

            ctx.stroke();
            lastX = x;
            lastY = y;
            e.preventDefault();
        });

        annotationCanvas.addEventListener("touchend", () => { isDrawing = false; });
    }

});







