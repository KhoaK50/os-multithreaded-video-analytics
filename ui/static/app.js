/**
 * CYBER SURVEILLANCE HUB - CLIENT LOGIC
 * Tích hợp Live Camera 30 FPS, CapCut Timeline Trimmer, Token Meter & Semantic Q&A.
 */

// Lucide / Radix Micro-SVG Icons (14-16px) - Anti-AI Slop
const ICONS = {
    play: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
    pause: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>',
    camera: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>',
    globe: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    mirror: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="4" y1="4" x2="9" y2="9"/></svg>',
    sun: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
    moon: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
    lightbulb: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/></svg>',
    sparkles: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>',
    filter: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>',
    activity: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    repeat: '<svg class="ui-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>',
    user: '<svg class="ui-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    users: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    users_lg: '<svg class="ui-icon empty-svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    clock: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    fileText: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    download: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
    upload: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
    search: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    zap: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    alertTriangle: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    film: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="17" x2="22" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/></svg>',
    x: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    refresh: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>',
    arrowRight: '<svg class="ui-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>',
    check: '<svg class="ui-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
};

// Theme Management (Dark / Light) with Radix Slate & WCAG AA Contrast
function initTheme() {
    const savedTheme = localStorage.getItem("app_theme") || "dark";
    setTheme(savedTheme);
}

function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
        localStorage.setItem("app_theme", theme);
    } catch (e) {
        // Ignore storage errors in restricted contexts
    }
    const themeIcon = document.getElementById("theme-icon");
    if (themeIcon) {
        themeIcon.innerHTML = theme === "light" ? ICONS.moon : ICONS.sun;
    }
}

function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    const next = current === "dark" ? "light" : "dark";
    setTheme(next);
}

// Custom Non-Blocking Toast Notification (Radix Slate - Anti-AI Slop)
function showToast(message, type = "info") {
    let container = document.getElementById("custom-toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "custom-toast-container";
        container.className = "custom-toast-container";
        document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.className = `custom-toast toast-${type}`;
    const icon = type === "error" ? ICONS.alertTriangle : (type === "warning" ? ICONS.alertTriangle : (type === "success" ? ICONS.check : ICONS.sparkles));
    const msgSpan = document.createElement("span");
    msgSpan.className = "toast-msg";
    msgSpan.textContent = String(message || "");
    toast.innerHTML = `<span class="toast-icon">${icon}</span>`;
    toast.appendChild(msgSpan);
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add("toast-fade-out");
        setTimeout(() => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 250);
    }, 4000);
}

// Intercept browser alert() and confirm() to eliminate default browser popups (Anti-AI Slop Rule 2)
window.alert = function(msg) {
    showToast(msg, "warning");
};
window.confirm = function(msg) {
    return true;
};


// Global State
let currentTab = "live";
let telemetryInterval = null;
let logsInterval = null;
let currentVideoData = null; // { video_path, stream_url, duration, filename }
let currentJobId = null;
let jobPollInterval = null;
let cachedLogs = [];
let cameraSettings = { mirror: true, anti_glare: true, denoise: true };
let isServerOnline = true;

// Video Analytics & Timeline Segmenter State
let currentAnalysisResult = null;
let currentSegments = [];
let currentHeatmapData = [];
let allEntitiesDetected = [];
let activeFocusSegment = null;
let isLoopingSegment = false;
let activeEntityFilter = 'all';
let currentResultDuration = 30.0;

// Helper an toàn: cập nhật textContent mà không bao giờ quăng lỗi null
function safeSetText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ==============================================================================
// INITIALIZATION
// ==============================================================================
document.addEventListener("DOMContentLoaded", () => {
    try {
        initTheme();
    } catch (e) {
        console.error("Lỗi initTheme:", e);
    }
    try {
        initTelemetry();
    } catch (e) {
        console.error("Lỗi initTelemetry:", e);
    }
    try {
        fetchCameraLogs();
        logsInterval = setInterval(fetchCameraLogs, 1000);
    } catch (e) {
        console.error("Lỗi fetchCameraLogs:", e);
    }
    try {
        setupDropzone();
    } catch (e) {
        console.error("Lỗi setupDropzone:", e);
    }
});

// ==============================================================================
// TAB NAVIGATION
// ==============================================================================
function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll(".nav-tab").forEach(btn => btn.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(pane => pane.classList.remove("active"));

    if (tab === "live") {
        const liveBtn = document.getElementById("tab-live-btn");
        const livePane = document.getElementById("tab-live");
        if (liveBtn) liveBtn.classList.add("active");
        if (livePane) livePane.classList.add("active");
        fetchTelemetry();
        fetchCameraLogs();
    } else {
        const vidBtn = document.getElementById("tab-video-btn");
        const vidPane = document.getElementById("tab-video");
        if (vidBtn) vidBtn.classList.add("active");
        if (vidPane) vidPane.classList.add("active");
    }
}

// ==============================================================================
// LIVE TELEMETRY & CAMERA CONTROL
// ==============================================================================
function initTelemetry() {
    fetchTelemetry();
    telemetryInterval = setInterval(fetchTelemetry, 1000);
}

async function fetchTelemetry() {
    try {
        const res = await fetch("/api/telemetry");
        if (!res.ok) return;
        const data = await res.json();

        if (!isServerOnline) {
            isServerOnline = true;
            console.info("[+] Đã kết nối lại máy chủ FastAPI thành công.");
        }

        // Cập nhật Floating Action Bubble & Realtime Quota Matrix Drawer (hoạt động trên cả 2 Tab)
        if (data.quota_matrix) {
            updateQuotaDrawerUI(data.quota_matrix, data);
        }
        if (data.tier_badge) {
            safeSetText("model-tier-badge", data.tier_badge);
        }

        // Nếu không ở Tab Trực Tiếp, bỏ qua cập nhật các thành phần dành riêng cho Camera
        if (currentTab !== "live") return;

        // Cập nhật số liệu vận hành Hệ điều hành
        safeSetText("live-fps", `${data.fps || 0} FPS`);
        safeSetText("live-consumer-fps", `${data.consumer_fps || data.fps || 30.0} FPS`);
        safeSetText("live-cpu", `${data.cpu_percent || 0}%`);
        safeSetText("live-vram", `${((data.gpu_vram_mb || 0) / 1024).toFixed(1)} / ${((data.gpu_vram_total_mb || 8192) / 1024).toFixed(1)} GB`);
        safeSetText("live-ram", `${data.ram_percent || 0}%`);

        // Cập nhật Bounded Buffer & Flow Control thời gian thực
        const qSize = data.queue_size !== undefined ? data.queue_size : (data.bounded_queue_size || 0);
        const qMax = data.queue_max !== undefined ? data.queue_max : (data.bounded_queue_capacity || 16);
        const droppedFrames = data.dropped_frames !== undefined ? data.dropped_frames : 0;
        const dropRate = data.drop_rate_pct !== undefined ? data.drop_rate_pct : 0.0;
        const hwmVal = data.high_water_mark !== undefined ? data.high_water_mark : 0;

        safeSetText("live-queue", `${qSize} / ${qMax} frames`);
        safeSetText("live-hwm-badge", `HWM: ${hwmVal}`);
        safeSetText("live-drop-frames", `${droppedFrames} frames`);
        safeSetText("live-drop-rate", `Drop: ${Number(dropRate).toFixed(1)}%`);

        // Cập nhật Nguyên ngữ Đồng bộ hóa & Trần bộ nhớ
        safeSetText("os-sync-mutex", `${(data.mutex_lock_count || 0).toLocaleString()} lượt`);
        safeSetText("os-sync-signals", `${(data.condition_signal_count || 0).toLocaleString()} tín hiệu`);
        safeSetText("os-sync-waits", `${((data.not_empty_wait_count || 0) + (data.not_full_wait_count || 0)).toLocaleString()} lượt chờ`);
        const ramCeil = data.ram_ceiling_mb !== undefined ? Number(data.ram_ceiling_mb).toFixed(2) : "42.19";
        safeSetText("os-sync-ram-ceiling", `${ramCeil} MB`);

        // Cập nhật Ma trận Trạng thái 4 Luồng Thực thi
        const tStates = data.thread_states || {};
        updateThreadStateBadge("ts-badge-producer", tStates.CamProducer || (data.producer_running ? "RUNNING" : "READY"));
        updateThreadStateBadge("ts-badge-edge", tStates.CamEdgeAI || (data.producer_running ? "RUNNING" : "READY"));
        updateThreadStateBadge("ts-badge-compositor", tStates.CamCompositor || (data.producer_running ? "RUNNING" : "READY"));
        updateThreadStateBadge("ts-badge-gemini", tStates.CamGeminiAI || (data.producer_running ? "WAITING" : "READY"));

        const prodBadge = document.getElementById("producer-thread-badge");
        if (prodBadge) {
            if (data.stress_test_active) {
                prodBadge.textContent = "XUNG KIỂM THỬ";
                prodBadge.className = "badge badge-warning mono";
            } else if (data.camera_running || data.producer_running) {
                prodBadge.textContent = "ĐANG THU NHẬN";
                prodBadge.className = "badge badge-safe mono";
            } else {
                prodBadge.textContent = "SẴN SÀNG";
                prodBadge.className = "badge badge-neutral mono";
            }
        }

        const queueBar = document.getElementById("queue-progress-bar");
        if (queueBar) {
            const pct = Math.min(100, Math.max(0, Math.round((qSize / Math.max(1, qMax)) * 100)));
            queueBar.style.width = `${pct}%`;
            if (pct >= 80) {
                queueBar.style.backgroundColor = "var(--accent-amber)";
            } else {
                queueBar.style.backgroundColor = "var(--accent-cyan)";
            }
        }

        const dropBadge = document.getElementById("live-drop-rate");
        if (dropBadge) {
            if (dropRate > 15.0) {
                dropBadge.className = "badge badge-danger mono";
            } else if (dropRate > 3.0) {
                dropBadge.className = "badge badge-warning mono";
            } else {
                dropBadge.className = "badge badge-neutral mono";
            }
        }

        // Cập nhật Biomechanics
        const bio = data.biomechanics || {};
        const isDanger = bio.is_danger;
        const threatBadge = document.getElementById("live-threat-badge");
        if (threatBadge) {
            threatBadge.className = isDanger ? "badge badge-danger" : "badge badge-safe";
            threatBadge.textContent = isDanger ? "NGUY HIỂM" : "AN TOÀN";
        }

        const angleDeg = Math.round(bio.angle || 90);
        safeSetText("live-angle-badge", `${angleDeg}°`);
        safeSetText("live-posture-text", bio.posture || "Ngồi thẳng");
        safeSetText("live-alert-text", bio.alert || "Khu vực an toàn");
        safeSetText("sidebar-posture-text", bio.posture || "Ngồi thẳng bình thường");
        safeSetText("sidebar-alert-text", bio.alert || "Khu vực an toàn");
        safeSetText("sidebar-angle-text", `${angleDeg}°`);

        const sidebarFill = document.getElementById("sidebar-angle-fill");
        if (sidebarFill) {
            const fillPct = Math.min(100, Math.max(5, (angleDeg / 90.0) * 100));
            sidebarFill.style.width = `${fillPct}%`;
        }

        // Camera Enhancer button states
        if (data.camera_settings) {
            cameraSettings = data.camera_settings;
            updateEnhancerButtonsUI();
        }

        // Cập nhật thẻ thống kê phiên trực tiếp (Live Session Summary Pills)
        if (data.session_risk_counts) {
            safeSetText("session-safe-count", data.session_risk_counts.safe || 0);
            safeSetText("session-warn-count", data.session_risk_counts.warning || 0);
            safeSetText("session-danger-count", data.session_risk_counts.danger || 0);
        }
        if (data.current_ergonomic_score !== undefined) {
            safeSetText("session-ergo-score", `${Math.round(data.current_ergonomic_score)} / 100`);
        }

        // Update camera offline overlay & status pills
        const offlineOverlay = document.getElementById("cam-offline-overlay");
        const toggleBtn = document.getElementById("btn-toggle-cam");
        const statusDot = document.getElementById("live-stream-status-dot");

        if (data.camera_running || isStreamingBrowserCam) {
            if (offlineOverlay) offlineOverlay.classList.add("hidden");
            const streamImg = document.getElementById("live-stream-img");
            if (streamImg && (!streamImg.src || streamImg.getAttribute("src") === "" || streamImg.src.endsWith("/"))) {
                streamImg.src = "/api/stream/live?t=" + Date.now();
            }
            if (toggleBtn) {
                toggleBtn.innerHTML = `${ICONS.pause}<span>Tắt Camera</span>`;
                toggleBtn.className = "btn btn-sm btn-danger-outline";
            }
            if (statusDot) {
                statusDot.style.background = "var(--accent-emerald)";
                statusDot.style.boxShadow = "none";
            }
            safeSetText("live-stream-status-text", `TRỰC TIẾP — ${Math.round(data.fps || 30)} FPS`);
        } else {
            if (offlineOverlay) offlineOverlay.classList.remove("hidden");
            if (toggleBtn) {
                toggleBtn.innerHTML = `${ICONS.play}<span>Bật Camera</span>`;
                toggleBtn.className = "btn btn-sm btn-primary";
            }
            if (statusDot) {
                statusDot.style.background = "var(--accent-crimson)";
                statusDot.style.boxShadow = "none";
            }
            safeSetText("live-stream-status-text", "ĐÃ TẮT CAMERA");
        }
    } catch (e) {
        if (isServerOnline) {
            isServerOnline = false;
            console.warn("[!] Máy chủ FastAPI tại 127.0.0.1:8000 đang ngắt kết nối hoặc đang khởi động lại.");
            safeSetText("live-stream-status-text", "MÁY CHỦ NGOẠI TUYẾN — python main.py");
            const statusDot = document.getElementById("live-stream-status-dot");
            if (statusDot) {
                statusDot.style.background = "var(--accent-amber)";
                statusDot.style.boxShadow = "none";
            }
        }
    }
}

async function toggleCamera(forceAction = null) {
    const toggleBtn = document.getElementById("btn-toggle-cam");
    let action = forceAction;
    if (!action) {
        const isCurrentlyActive = (toggleBtn && (toggleBtn.textContent.includes("Tắt") || toggleBtn.textContent.includes("Tạm dừng"))) || isStreamingBrowserCam;
        action = isCurrentlyActive ? "stop" : "start";
    }

    if (action === "stop") {
        // 1. Dừng triệt để luồng webcam trình duyệt (chấm dứt gửi client frames)
        stopBrowserWebcam();

        // 2. Gửi lệnh dừng LiveCameraPipeline trên máy chủ
        try {
            await fetch(`/api/camera/toggle?action=stop`, { method: "POST" });
        } catch (e) {
            console.error("Lỗi dừng camera máy chủ:", e);
        }

        // 3. Cập nhật UI ngay tức thì để người dùng cảm nhận phản hồi ngay
        if (toggleBtn) {
            toggleBtn.innerHTML = `${ICONS.play}<span>Bật Camera</span>`;
            toggleBtn.className = "btn btn-sm btn-primary";
        }
        const offlineOverlay = document.getElementById("cam-offline-overlay");
        if (offlineOverlay) offlineOverlay.classList.remove("hidden");
        const statusDot = document.getElementById("live-stream-status-dot");
        if (statusDot) {
            statusDot.style.background = "var(--accent-crimson)";
        }
        safeSetText("live-stream-status-text", "ĐÃ TẮT CAMERA");

        // 4. Reset khung stream sang ảnh chờ
        const img = document.getElementById("live-stream-img");
        if (img) img.src = "/api/stream/live?t=" + Date.now();
        await fetchTelemetry();
        return;
    }

    if (action === "start") {
        try {
            const res = await fetch(`/api/camera/toggle?action=start`, { method: "POST" });
            const data = await res.json();

            // Nếu máy chủ báo không có camera vật lý trực tiếp (VD: chạy trên Google Colab / máy ảo VPS),
            // tự động kích hoạt Webcam Trình Duyệt để người dùng không cần bấm 2 nút riêng biệt!
            if (data && data.device_available === false) {
                console.info("[i] Máy chủ không có camera vật lý. Tự động chuyển hướng sang Webcam Trình Duyệt...");
                await toggleBrowserWebcam();
            } else {
                const img = document.getElementById("live-stream-img");
                if (img) img.src = "/api/stream/live?t=" + Date.now();
                const offlineOverlay = document.getElementById("cam-offline-overlay");
                if (offlineOverlay) offlineOverlay.classList.add("hidden");
            }

            if (toggleBtn) {
                toggleBtn.innerHTML = `${ICONS.pause}<span>Tắt Camera</span>`;
                toggleBtn.className = "btn btn-sm btn-danger-outline";
            }
            await fetchTelemetry();
        } catch (e) {
            console.error("Lỗi khởi động camera:", e);
            showToast("Lỗi kết nối máy chủ khi bật camera", "error");
        }
    }
}

// Quản lý Webcam Trình Duyệt (HTML5 getUserMedia - dành cho Colab / Máy ảo)
let browserCamStream = null;
let browserCamInterval = null;
let isStreamingBrowserCam = false;

async function toggleBrowserWebcam() {
    if (isStreamingBrowserCam) {
        stopBrowserWebcam();
        return;
    }

    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showToast("Trình duyệt không hỗ trợ hoặc đang chặn quyền truy cập Camera. Hãy đảm bảo bạn truy cập qua link HTTPS hoặc localhost và đã bấm Cho Phép.", "error");
            return;
        }

        // Đảm bảo backend đã khởi động pipeline để nhận khung hình
        await fetch(`/api/camera/toggle?action=start`, { method: "POST" });

        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 640 },
                height: { ideal: 480 },
                facingMode: "user"
            },
            audio: false
        });

        browserCamStream = stream;
        const video = document.getElementById("client-webcam-video");
        if (video) {
            video.srcObject = stream;
            await video.play();
        }

        isStreamingBrowserCam = true;

        const toggleBtn = document.getElementById("btn-toggle-cam");
        if (toggleBtn) {
            toggleBtn.innerHTML = `${ICONS.pause}<span>Tắt Camera</span>`;
            toggleBtn.className = "btn btn-sm btn-danger-outline";
        }
        const fallbackBtn = document.getElementById("btn-browser-cam-fallback");
        if (fallbackBtn) {
            fallbackBtn.innerHTML = `${ICONS.pause}<span>Tắt Webcam Trình Duyệt</span>`;
            fallbackBtn.classList.add("active-toggle");
        }

        // Tự động kết nối lại luồng stream hiển thị
        const liveImg = document.getElementById("live-stream-img");
        if (liveImg) {
            liveImg.src = "/api/stream/live?t=" + Date.now();
        }
        const offlineOverlay = document.getElementById("cam-offline-overlay");
        if (offlineOverlay) offlineOverlay.classList.add("hidden");

        // Bắt đầu vòng lặp gửi khung hình (Adaptive Ping-Pong)
        const canvas = document.getElementById("client-webcam-canvas");
        canvas.width = 480;
        canvas.height = 360;
        const ctx = canvas.getContext("2d");

        async function streamLoop() {
            while (isStreamingBrowserCam) {
                if (video && video.readyState >= 2) {
                    ctx.drawImage(video, 0, 0, 480, 360);
                    try {
                        const blob = await new Promise((resolve) => {
                            canvas.toBlob(resolve, "image/jpeg", 0.45);
                        });
                        if (blob && isStreamingBrowserCam) {
                            const formData = new FormData();
                            formData.append("file", blob, "webcam.jpg");
                            await fetch("/api/camera/client_frame", {
                                method: "POST",
                                body: formData
                            });
                        }
                    } catch (e) {
                        // Bỏ qua lỗi mạng tạm thời
                    }
                }
                // Nghỉ nhẹ 30ms giữa các frame để giữ đường truyền ổn định
                await new Promise((r) => setTimeout(r, 30));
            }
        }

        streamLoop();

    } catch (err) {
        console.error("Lỗi mở webcam trình duyệt:", err);
        showToast("Không thể mở camera thiết bị: " + (err.message || "Bị từ chối quyền truy cập"), "error");
        stopBrowserWebcam();
    }
}

function stopBrowserWebcam() {
    isStreamingBrowserCam = false;
    if (browserCamInterval) {
        clearInterval(browserCamInterval);
        browserCamInterval = null;
    }
    if (browserCamStream) {
        browserCamStream.getTracks().forEach(track => track.stop());
        browserCamStream = null;
    }
    const video = document.getElementById("client-webcam-video");
    if (video) {
        video.srcObject = null;
    }
    const fallbackBtn = document.getElementById("btn-browser-cam-fallback");
    if (fallbackBtn) {
        fallbackBtn.innerHTML = `${ICONS.globe}<span>Dùng Webcam Trình Duyệt</span>`;
        fallbackBtn.classList.remove("active-toggle");
    }
}


// ==============================================================================
// CAMERA ENHANCER CONTROLS
// ==============================================================================
async function toggleCameraEnhancer(settingKey) {
    const newVal = !cameraSettings[settingKey];
    cameraSettings[settingKey] = newVal;
    updateEnhancerButtonsUI();

    try {
        await fetch("/api/camera/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ [settingKey]: newVal })
        });
    } catch (e) {
        console.error("Lỗi cập nhật bộ lọc camera:", e);
    }
}

function updateEnhancerButtonsUI() {
    const mirrorBtn = document.getElementById("btn-toggle-mirror");
    const glareBtn = document.getElementById("btn-toggle-glare");
    const denoiseBtn = document.getElementById("btn-toggle-denoise");

    if (mirrorBtn) {
        mirrorBtn.innerHTML = `${ICONS.mirror}<span>Lật gương: ${cameraSettings.mirror ? "BẬT" : "TẮT"}</span>`;
        mirrorBtn.classList.toggle("active-toggle", !!cameraSettings.mirror);
    }
    if (glareBtn) {
        glareBtn.innerHTML = `${ICONS.lightbulb}<span>Chống chói: ${cameraSettings.anti_glare ? "BẬT" : "TẮT"}</span>`;
        glareBtn.classList.toggle("active-toggle", !!cameraSettings.anti_glare);
    }
    if (denoiseBtn) {
        denoiseBtn.innerHTML = `${ICONS.filter}<span>Khử nhiễu: ${cameraSettings.denoise ? "BẬT" : "TẮT"}</span>`;
        denoiseBtn.classList.toggle("active-toggle", !!cameraSettings.denoise);
    }
}

// ==============================================================================
// REAL-TIME BEHAVIOR EVENT LOGS & SNAPSHOTS
// ==============================================================================
async function fetchCameraLogs() {
    if (currentTab !== "live") return;
    try {
        const res = await fetch("/api/camera/logs");
        if (!res.ok) return;
        const data = await res.json();
        const logs = data.logs || [];

        // Cập nhật huy hiệu trạng thái AI (Cloud vs 429 Quota Exceeded vs Heuristic Cục bộ)
        const quotaBadge = document.getElementById("gemini-quota-badge");
        if (quotaBadge && data.gemini_status) {
            if (data.gemini_status === "quota_exceeded") {
                quotaBadge.textContent = "429 Quota Exceeded — AI Tự Hành Cục Bộ";
                quotaBadge.className = "badge badge-warn mono";
            } else if (data.gemini_status === "heuristic_offline") {
                quotaBadge.textContent = "AI Tự Hành Ngoại Tuyến — 0 Token";
                quotaBadge.className = "badge badge-safe mono";
            } else {
                quotaBadge.textContent = "13 RPM Free Quota";
                quotaBadge.className = "badge badge-safe mono";
            }
        }

        // So sánh tránh render lại làm nhấp nháy UI
        if (logs.length === cachedLogs.length && JSON.stringify(logs) === JSON.stringify(cachedLogs)) {
            return;
        }
        cachedLogs = logs;

        // Cập nhật số lượng
        const countBadge = document.getElementById("log-count-badge");
        if (countBadge) countBadge.textContent = `${logs.length} sự kiện`;

        renderBehaviorTable(logs);
        if (typeof isLiveParallelActive !== "undefined" && isLiveParallelActive && typeof updateLiveParallelReportsAndLogs === "function") {
            updateLiveParallelReportsAndLogs();
        }
    } catch (e) {
        if (isServerOnline) {
            console.warn("Chưa lấy được nhật ký hành vi:", e.message || e);
        }
    }
}

function getModelTierBadge(tierKey) {
    const key = (tierKey || "").toLowerCase();
    if (key.includes("tier_1") || key.includes("3.8") || key.includes("2.5") || key.includes("2.0")) {
        return `<span class="badge badge-safe mono" style="font-size: 11px; padding: 2px 7px; white-space: nowrap;">Tier-1 Gemini 3.8</span>`;
    } else if (key.includes("tier_2") || key.includes("3.5") || key.includes("1.5")) {
        return `<span class="badge badge-warning mono" style="font-size: 11px; padding: 2px 7px; white-space: nowrap;">Tier-2 Gemini 3.5</span>`;
    } else if (key.includes("local") || key.includes("heuristic") || key.includes("tier_3")) {
        return `<span class="badge badge-outline mono" style="font-size: 11px; padding: 2px 7px; white-space: nowrap;">AI Tự Hành</span>`;
    }
    return `<span class="badge badge-safe mono" style="font-size: 11px; padding: 2px 7px; white-space: nowrap;">Tier-1 Gemini 3.8</span>`;
}

function renderBehaviorTable(logs) {
    const tbody = document.getElementById("behavior-log-tbody");
    if (!tbody) return;

    if (!logs || logs.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="7" class="empty-cell">
                    <div class="empty-state-box">
                        <span class="empty-icon"><svg class="ui-icon empty-svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg></span>
                        <p class="empty-title">Chưa có bản ghi nhận diện tư thế công thái học</p>
                        <span class="empty-sub">Khởi động camera hoặc nạp luồng video để hệ thống bắt đầu thu nhận khung hình và phân tích hành vi theo chu kỳ 4 giây.</span>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    let html = "";
    for (const item of logs) {
        const isDanger = item.severity === "danger";
        const isWarn = item.severity === "warning";
        const badgeClass = isDanger ? "badge-danger" : (isWarn ? "badge-warning" : "badge-safe");
        const rowClass = isDanger ? "row-danger" : "";
        const predText = item.prediction_next_4s || "Duy trì trạng thái trong 4s tới";

        html += `
            <tr class="${rowClass}">
                <td>
                    <span class="log-code-badge">${escapeHtml(item.code || item.id)}</span>
                </td>
                <td class="mono">${escapeHtml(item.timestamp || "--:--:--")}</td>
                <td>
                    ${getModelTierBadge(item.model_tier)}
                </td>
                <td>
                    <span class="badge ${badgeClass}">${escapeHtml(item.action)}</span>
                </td>
                <td class="desc-cell">${escapeHtml(item.description)}</td>
                <td class="prediction-cell">
                    <div class="prediction-badge">
                        <span class="pred-icon">${ICONS.sparkles}</span>
                        <span class="pred-text">${escapeHtml(predText)}</span>
                    </div>
                </td>
                <td style="text-align: center;">
                    <img 
                        src="${escapeHtml(item.snapshot_url)}" 
                        alt="${escapeHtml(item.action)}" 
                        class="snapshot-thumb" 
                        loading="lazy"
                        onclick="openSnapshotModal('${escapeHtml(item.snapshot_url)}', '${escapeHtml(item.id || item.code)}', '${escapeHtml(item.action)}', '${escapeHtml(item.timestamp)}', '${escapeHtml(item.description)}', '${escapeHtml(predText)}')"
                        title="Nhấn để phóng to ảnh chứng cứ và xem chi tiết"
                    />
                </td>
            </tr>
        `;
    }
    tbody.innerHTML = html;
}

async function captureManualSnapshot() {
    const snapBtn = document.getElementById("btn-manual-snap");
    if (snapBtn) {
        snapBtn.disabled = true;
        snapBtn.innerHTML = `${ICONS.camera}<span>Đang chụp...</span>`;
    }
    try {
        const res = await fetch("/api/camera/snapshot", { method: "POST" });
        const data = await res.json();
        if (data.status === "success") {
            await fetchCameraLogs();
        } else {
            showToast("Không thể chụp ảnh: " + (data.message || "Vui lòng bật camera"), "warning");
        }
    } catch (e) {
        showToast("Lỗi khi gửi lệnh chụp snapshot: " + e, "error");
    } finally {
        if (snapBtn) {
            snapBtn.disabled = false;
            snapBtn.innerHTML = `${ICONS.camera}<span>Chụp Snapshot</span>`;
        }
    }
}

async function clearLogs() {
    if (!cachedLogs || cachedLogs.length === 0) {
        showToast("Nhật ký hiện tại đang trống.", "warning");
        return;
    }
    try {
        await fetch("/api/camera/logs/clear", { method: "POST" });
        cachedLogs = [];
        renderBehaviorTable([]);
        const countBadge = document.getElementById("log-count-badge");
        if (countBadge) countBadge.textContent = "0 sự kiện";
        showToast("Đã xóa sạch toàn bộ nhật ký hành vi.", "info");
    } catch (e) {
        showToast("Lỗi khi xóa nhật ký: " + e, "error");
    }
}

function exportLogsToCSV() {
    if (!cachedLogs || cachedLogs.length === 0) {
        showToast("Chưa có sự kiện nào trong nhật ký để xuất CSV.", "warning");
        return;
    }

    const headers = ["STT", "Mã sự kiện", "Thời gian", "Hành vi 4s gần nhất", "Mô tả chi tiết ngữ cảnh", "Dự đoán 4s tiếp theo", "Đường dẫn snapshot", "Mức độ an toàn"];
    const rows = cachedLogs.map((item, idx) => [
        idx + 1,
        `"${(item.code || item.id || '').replace(/"/g, '""')}"`,
        `"${(item.timestamp || '').replace(/"/g, '""')}"`,
        `"${(item.action || '').replace(/"/g, '""')}"`,
        `"${(item.description || '').replace(/"/g, '""')}"`,
        `"${(item.prediction_next_4s || '').replace(/"/g, '""')}"`,
        `"${(item.snapshot_url || '').replace(/"/g, '""')}"`,
        `"${(item.severity || 'safe').replace(/"/g, '""')}"`
    ]);

    const csvContent = "\uFEFF" + [headers.join(","), ...rows.map(r => r.join(","))].join("\r\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const nowStr = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
    link.setAttribute("href", url);
    link.setAttribute("download", `nhat_ky_hanh_vi_gemini_${nowStr}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

// ==============================================================================
// SNAPSHOT MODAL VIEWER
// ==============================================================================
function openSnapshotModal(url, code, action, time, desc, pred) {
    const modal = document.getElementById("snapshot-modal");
    if (!modal) return;

    document.getElementById("modal-img").src = url;
    document.getElementById("modal-code").textContent = code || "#001";
    document.getElementById("modal-action-title").textContent = action || "Bằng chứng hành vi";
    document.getElementById("modal-time").textContent = time || "--:--:--";
    document.getElementById("modal-desc").textContent = desc || "--";
    
    const predEl = document.getElementById("modal-pred");
    if (predEl) predEl.textContent = pred || "Duy trì trạng thái trong 4 giây tiếp theo";

    const downloadLink = document.getElementById("modal-download-link");
    if (downloadLink) {
        downloadLink.href = url;
        downloadLink.download = `${code || 'snapshot'}_${Date.now()}.jpg`;
    }

    modal.classList.remove("hidden");
}

function closeSnapshotModal(e) {
    if (e && e.target && e.target !== e.currentTarget && !e.target.classList.contains("modal-close-btn") && !e.target.classList.contains("btn-primary")) {
        return;
    }
    const modal = document.getElementById("snapshot-modal");
    if (modal) modal.classList.add("hidden");
}

// ==============================================================================
// SEGMENT DETAIL MODAL VIEWER
// ==============================================================================
function openSegmentDetailModal(segId) {
    if (!currentSegments || currentSegments.length === 0) return;
    const seg = currentSegments.find(s => s.segment_id === segId);
    if (!seg) return;

    const modal = document.getElementById("segment-detail-modal");
    if (!modal) return;

    safeSetText("seg-modal-id", seg.segment_id || "#SEG--");
    safeSetText("seg-modal-timerange", seg.time_range || "--:-- - --:--");
    
    const badgeEl = document.getElementById("seg-modal-severity-badge");
    if (badgeEl) {
        const numScore = parseFloat(seg.danger_score || 0);
        const isDanger = numScore >= 8.0 || seg.severity === "danger";
        const isWarn = (!isDanger && (numScore >= 4.0 || seg.severity === "warning"));
        if (isDanger) {
            badgeEl.className = "badge badge-danger mono";
            badgeEl.textContent = "NGUY HIỂM";
        } else if (isWarn) {
            badgeEl.className = "badge badge-warning mono";
            badgeEl.textContent = "CẢNH BÁO";
        } else {
            badgeEl.className = "badge badge-safe mono";
            badgeEl.textContent = "AN TOÀN";
        }
    }

    // 0. Snapshot Image Preview
    const snapImg = document.getElementById("seg-modal-snapshot-img");
    const snapContainer = document.getElementById("seg-modal-snapshot-container");
    if (snapImg && snapContainer) {
        if (seg.snapshot_url) {
            snapImg.src = seg.snapshot_url;
            snapContainer.classList.remove("hidden");
        } else {
            snapContainer.classList.add("hidden");
        }
    }

    // 1. Summary
    const summaryVal = (seg.scene_summary || seg.context_description || "Phân đoạn ghi nhận vận động ổn định của các đối tượng.").trim();
    safeSetText("seg-modal-summary", summaryVal);

    // 2. Entity Detail Cards (Rộng rãi, tập trung vào vị trí trên ảnh chụp và hành vi cốt lõi)
    const cardsContainer = document.getElementById("seg-modal-entity-matrix");
    if (cardsContainer) {
        cardsContainer.innerHTML = "";
        const entities = (seg.entities || []).filter(e => e && String(e.id || "") !== "KHÔNG GIAN" && e.raw_id !== "ALL");
        if (entities.length === 0) {
            cardsContainer.innerHTML = `<div class="empty-entity-sub">Không có thông tin đối tượng trong phân đoạn.</div>`;
        } else {
            entities.forEach(ent => {
                const rawId = String(ent.id || "");
                const idMatch = rawId.match(/ID\s*#?(\d+)/i);
                const idTag = idMatch ? `ID #${idMatch[1].padStart(2, '0')}` : (ent.raw_id || "ID #--");
                let actorName = ent.actor_label || rawId.replace(/\(?ID\s*#?\d+\)?/i, '').replace(/[\(\)—-]/g, '').trim();
                if (/^(đối tượng|chủ thể)\s*#?\d+/i.test(actorName)) actorName = "";

                const rawAnchor = (ent.distinctive_anchor || "").replace(/[\(\)\[\]]/g, '').trim();
                const anchorText = (/^(khu vực|đối tượng|chủ thể)\s*#?\d+/i.test(rawAnchor) || rawAnchor === actorName) ? "" : rawAnchor;

                const actionText = (ent.action || "Sinh hoạt tự nhiên").replace(/[\(\)]/g, '').trim();
                const postureText = (ent.posture || "").replace(/[\(\)]/g, '').trim();
                const postureCore = postureText.replace(/^(đang|tư\s*thế)\s+/i, '').trim();
                const isPostureRedundant = !postureCore ||
                    actionText.toLowerCase().includes(postureText.toLowerCase()) ||
                    actionText.toLowerCase().includes(postureCore.toLowerCase());
                const combinedBehavior = (!isPostureRedundant)
                    ? `${actionText} · ${postureText}`
                    : actionText;

                const effEntSev = seg.severity === "safe"
                    ? "safe"
                    : (seg.severity === "warning" && ent.severity === "danger" ? "warning" : (ent.severity || "safe"));

                const cleanRoleStr = (ent.role || "").replace(/[\(\)]/g, '·').replace(/\s*·\s*$/, '').trim();
                let roleBadgeText = "";
                let roleClass = "role-safe";
                if (effEntSev === "danger") {
                    if (cleanRoleStr && cleanRoleStr !== "An toàn" && cleanRoleStr !== "Bình thường") {
                        roleBadgeText = cleanRoleStr;
                    } else {
                        roleBadgeText = "Trực tiếp xung đột";
                    }
                    roleClass = "role-danger";
                } else if (effEntSev === "warning") {
                    if (cleanRoleStr && cleanRoleStr !== "An toàn" && cleanRoleStr !== "Bình thường") {
                        roleBadgeText = cleanRoleStr;
                    } else {
                        roleBadgeText = "Đối đầu / Phòng thủ";
                    }
                    roleClass = "role-warn";
                } else {
                    if (seg.severity === "danger" || seg.severity === "warning") {
                        if (cleanRoleStr && (cleanRoleStr.toLowerCase().includes("ngoài cuộc") || cleanRoleStr.toLowerCase().includes("quan sát") || cleanRoleStr.toLowerCase().includes("can ngăn"))) {
                            roleBadgeText = cleanRoleStr.toLowerCase().startsWith("an toàn") ? cleanRoleStr : `An toàn · ${cleanRoleStr}`;
                        } else {
                            roleBadgeText = "An toàn · Người ngoài cuộc / Quan sát";
                        }
                    } else {
                        const safeRoleClean = cleanRoleStr
                            .replace(/^(người\s+ngoài\s+cuộc|ngoài\s+cuộc)\s*[·/\-:]?\s*/i, '')
                            .replace(/\b(người\s+ngoài\s+cuộc|ngoài\s+cuộc)\b/gi, '')
                            .replace(/^[·/\-:\s]+|[·/\-:\s]+$/g, '')
                            .trim();
                        if (safeRoleClean && !["An toàn", "Bình thường", "Người quan sát", "Không gian"].includes(safeRoleClean)) {
                            roleBadgeText = safeRoleClean;
                        } else {
                            roleBadgeText = "An toàn";
                        }
                    }
                    roleClass = "role-safe";
                }

                const entBadgeClass = effEntSev === "danger" ? "tag-danger" : (effEntSev === "warning" ? "tag-warning" : "tag-safe");
                const cardBorderClass = effEntSev === "danger" ? "edc-card-danger" : (effEntSev === "warning" ? "edc-card-warn" : "edc-card-safe");
                const headerTitle = actorName || anchorText || idTag;

                const card = document.createElement("div");
                card.className = `entity-detail-card ${cardBorderClass}`;
                card.innerHTML = `
                    <div class="edc-header">
                        <div class="edc-identity">
                            <span class="entity-tag ${entBadgeClass} mono">${idTag}</span>
                            <strong class="edc-actor-title">${escapeHtml(headerTitle)}</strong>
                        </div>
                        <span class="entity-role-badge ${roleClass}">${escapeHtml(roleBadgeText)}</span>
                    </div>
                    <div class="edc-body">
                        ${anchorText && anchorText !== headerTitle ? `
                        <div class="edc-field-row">
                            <span class="edc-label">Vị trí trên ảnh chụp:</span>
                            <span class="edc-val">${escapeHtml(anchorText)}</span>
                        </div>` : ''}
                        <div class="edc-field-row">
                            <span class="edc-label">Hành vi &amp; tư thế:</span>
                            <span class="edc-val edc-action-text">${escapeHtml(combinedBehavior)}</span>
                        </div>
                    </div>
                `;
                cardsContainer.appendChild(card);
            });
        }
    }

    // 3. Detailed Narrative (Loại bỏ việc lặp lại câu tóm tắt hoặc câu sáo rỗng)
    let narrativeText = (seg.detailed_narrative || seg.context_description || summaryVal).trim();
    if (narrativeText.length > summaryVal.length && narrativeText.startsWith(summaryVal)) {
        narrativeText = narrativeText.slice(summaryVal.length).replace(/^[\s.—-]+/, '').trim();
    }
    safeSetText("seg-modal-narrative", narrativeText || summaryVal);

    const focalBox = document.getElementById("seg-modal-focal-box");
    const focalText = document.getElementById("seg-modal-focal-text");
    if (focalBox && focalText) {
        if (seg.focal_actors_desc && !narrativeText.includes(seg.focal_actors_desc)) {
            focalText.textContent = seg.focal_actors_desc;
            focalBox.classList.remove("hidden");
        } else {
            focalBox.classList.add("hidden");
        }
    }

    const predBox = document.getElementById("seg-modal-pred-box");
    const predText = document.getElementById("seg-modal-pred-text");
    if (predBox && predText) {
        if (seg.prediction_next_4s) {
            predText.textContent = seg.prediction_next_4s;
            predBox.classList.remove("hidden");
        } else {
            predBox.classList.add("hidden");
        }
    }

    // 4. Telemetry Breakdown Grid
    const telemContainer = document.getElementById("seg-modal-telemetry");
    if (telemContainer) {
        telemContainer.innerHTML = "";
        const tb = seg.telemetry_breakdown || {};
        const maxVelVal = tb.max_velocity !== undefined ? tb.max_velocity : (tb.strike_velocity || 0);
        const maxVelStr = typeof maxVelVal === "number" ? `${maxVelVal} px/s` : String(maxVelVal);
        const minDistVal = tb.min_distance !== undefined ? tb.min_distance : (tb.proximity_dist || null);
        const minDistStr = typeof minDistVal === "number" ? `${minDistVal} px` : (minDistVal ? String(minDistVal) : '> 1.5 m');
        const dominantPosture = (tb.dominant_posture || tb.posture_state || 'Bình thường').replace(/[\(\)]/g, '').trim();
        const scoreVal = typeof seg.danger_score === 'number' ? seg.danger_score : parseFloat(seg.danger_score || 0);

        const items = [
            { label: "Vận tốc cử động tối đa", val: maxVelStr, tip: "Tốc độ di chuyển hoặc vung tay chân lớn nhất ghi nhận được" },
            { label: "Khoảng cách tiếp cận", val: minDistStr, tip: "Khoảng cách đo đạc gần nhất giữa các đối tượng" },
            { label: "Tư thế nhận diện", val: dominantPosture, tip: "Tư thế chủ đạo được thẩm định trong phân đoạn" },
            { label: "Điểm nguy cơ tổng hợp", val: `${scoreVal.toFixed(1)} / 10`, tip: "Điểm nguy cơ đa biến kết hợp động học và thị giác" }
        ];

        items.forEach(it => {
            const card = document.createElement("div");
            card.className = "telem-modal-card";
            card.title = it.tip;
            card.innerHTML = `
                <span class="tmc-label">${escapeHtml(it.label)}</span>
                <strong class="tmc-val mono">${escapeHtml(it.val)}</strong>
            `;
            telemContainer.appendChild(card);
        });
    }

    // 5. Seek button
    const seekBtn = document.getElementById("seg-modal-seek-btn");
    if (seekBtn) {
        seekBtn.onclick = () => {
            closeSegmentDetailModal();
            focusTimelineSegment(seg.start_sec, seg.end_sec, seg.segment_id, seg.scene_summary);
        };
    }

    modal.classList.remove("hidden");
}

function closeSegmentDetailModal(e) {
    if (e && e.target && e.target !== e.currentTarget && !e.target.classList.contains("modal-close-btn") && !e.target.classList.contains("btn-primary")) {
        return;
    }
    const modal = document.getElementById("segment-detail-modal");
    if (modal) modal.classList.add("hidden");
}

function toggleTelemetryPanel() {
    const panel = document.getElementById("telemetry-floating-panel");
    const backdrop = document.getElementById("telemetry-backdrop");
    const statusBadge = document.getElementById("btn-telemetry-status");
    const toggleBtn = document.getElementById("btn-toggle-telemetry");

    if (!panel) return;
    const isHidden = panel.classList.contains("hidden");

    if (isHidden) {
        panel.classList.remove("hidden");
        if (backdrop) backdrop.classList.remove("hidden");
        if (statusBadge) {
            statusBadge.textContent = "HIỆN";
            statusBadge.className = "badge badge-safe mono";
        }
        if (toggleBtn) {
            toggleBtn.classList.add("active-toggle");
        }
    } else {
        panel.classList.add("hidden");
        if (backdrop) backdrop.classList.add("hidden");
        if (statusBadge) {
            statusBadge.textContent = "ẨN";
            statusBadge.className = "badge badge-neutral mono";
        }
        if (toggleBtn) {
            toggleBtn.classList.remove("active-toggle");
        }
    }
}

function closeTelemetryPanel() {
    const panel = document.getElementById("telemetry-floating-panel");
    const backdrop = document.getElementById("telemetry-backdrop");
    const statusBadge = document.getElementById("btn-telemetry-status");
    const toggleBtn = document.getElementById("btn-toggle-telemetry");

    if (panel) panel.classList.add("hidden");
    if (backdrop) backdrop.classList.add("hidden");
    if (statusBadge) {
        statusBadge.textContent = "ẨN";
        statusBadge.className = "badge badge-neutral mono";
    }
    if (toggleBtn) {
        toggleBtn.classList.remove("active-toggle");
    }
}

function openTelemetryPanel() {
    const panel = document.getElementById("telemetry-floating-panel");
    const backdrop = document.getElementById("telemetry-backdrop");
    const statusBadge = document.getElementById("btn-telemetry-status");
    const toggleBtn = document.getElementById("btn-toggle-telemetry");

    if (panel) panel.classList.remove("hidden");
    if (backdrop) backdrop.classList.remove("hidden");
    if (statusBadge) {
        statusBadge.textContent = "HIỆN";
        statusBadge.className = "badge badge-safe mono";
    }
    if (toggleBtn) {
        toggleBtn.classList.add("active-toggle");
    }
}

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        closeSnapshotModal();
        closeSegmentDetailModal();
        closeTelemetryPanel();
    }
});

function escapeHtml(text) {
    if (text === null || text === undefined) return "";
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// ==============================================================================
// TAB 2: SOURCE TOGGLE & DROPZONE
// ==============================================================================
function switchSourceMode(mode) {
    const localBtn = document.getElementById("src-local-btn");
    const urlBtn = document.getElementById("src-url-btn");
    const localZone = document.getElementById("source-local-zone");
    const urlZone = document.getElementById("source-url-zone");

    if (mode === "local") {
        localBtn.classList.add("active");
        urlBtn.classList.remove("active");
        localZone.classList.remove("hidden");
        urlZone.classList.add("hidden");
    } else {
        urlBtn.classList.add("active");
        localBtn.classList.remove("active");
        urlZone.classList.remove("hidden");
        localZone.classList.add("hidden");
    }
}

function setupDropzone() {
    const dropzone = document.getElementById("video-dropzone");
    if (!dropzone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.style.borderColor = "var(--accent-cyan)", false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.style.borderColor = "var(--border-strong)", false);
    });

    dropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            uploadFile(files[0]);
        }
    });
}

function handleFileSelected(event) {
    const file = event.target.files[0];
    if (file) {
        uploadFile(file);
    }
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append("file", file);

    const sizeMB = Math.max(0.1, file.size / (1024 * 1024));
    const estUploadSec = Math.max(1, Math.round(sizeMB / 18 + 1));
    const dropzone = document.getElementById("video-dropzone");
    dropzone.innerHTML = `<div class="dropzone-content"><span class="spinner"></span><h4>Đang nạp tệp video (${sizeMB.toFixed(1)} MB) — Dự kiến hoàn tất: ~${estUploadSec} giây...</h4></div>`;

    try {
        const res = await fetch("/api/video/upload", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (data.status === "success") {
            loadVideoIntoTrimmer(data);
        } else {
            alert("Lỗi tải video: " + JSON.stringify(data));
        }
    } catch (e) {
        alert("Lỗi kết nối khi tải video: " + e);
    } finally {
        resetDropzoneUI();
    }
}

function resetDropzoneUI() {
    const dropzone = document.getElementById("video-dropzone");
    if (!dropzone) return;
    dropzone.innerHTML = `
        <input type="file" id="video-file-input" accept="video/mp4,video/avi,video/quicktime,video/x-matroska,video/webm,video/x-flv,video/x-ms-wmv,video/x-m4v" style="display:none" onchange="handleFileSelected(event)">
        <div class="dropzone-content">
            <span class="drop-icon">${ICONS.upload}</span>
            <h4>Kéo thả video vào đây, hoặc <span class="highlight">nhấn để chọn file</span></h4>
            <p class="drop-hint">Định dạng video được hỗ trợ: <strong>.mp4, .avi, .mov, .mkv, .webm, .flv, .wmv, .m4v</strong> (Tối đa 150MB)</p>
            <p class="drop-subhint text-muted">Lưu ý: Không hỗ trợ tệp ảnh động .gif (phân tích động học AI yêu cầu video có luồng thời gian thực chuẩn).</p>
        </div>
    `;
}

// Load sample video button
function loadSampleVideo() {
    const sampleData = {
        video_path: "demo_synthetic.mp4",
        filename: "demo_synthetic.mp4",
        stream_url: "/api/video/stream_file/demo_synthetic.mp4",
        duration: 10.0
    };
    loadVideoIntoTrimmer(sampleData);
}

let currentProbedURLData = null;

function parseTimeToSeconds(input) {
    if (!input) return 0;
    const str = String(input).trim();
    if (str.includes(":")) {
        const parts = str.split(":");
        if (parts.length === 2) {
            return (parseFloat(parts[0]) || 0) * 60 + (parseFloat(parts[1]) || 0);
        } else if (parts.length === 3) {
            return (parseFloat(parts[0]) || 0) * 3600 + (parseFloat(parts[1]) || 0) * 60 + (parseFloat(parts[2]) || 0);
        }
    }
    return parseFloat(str) || 0;
}

function setSlicePreset(startSec, endSec) {
    const sInput = document.getElementById("url-slice-start");
    const eInput = document.getElementById("url-slice-end");
    if (sInput) sInput.value = formatTime(startSec);
    if (eInput) eInput.value = formatTime(endSec);
}

function loadSampleDemoURL() {
    const urlInput = document.getElementById("video-url-input");
    if (urlInput) {
        urlInput.value = "https://www.youtube.com/watch?v=GeLhuvhyWuM&t=698s";
        handleURLImport();
    }
}

// Handle Web URL Import (YouTube, etc.)
async function handleURLImport() {
    const urlInput = document.getElementById("video-url-input");
    const url = urlInput.value.trim();
    if (!url) {
        showToast("Vui lòng dán liên kết video YouTube hoặc liên kết trực tiếp.", "warning");
        return;
    }

    const spinner = document.getElementById("url-btn-spinner");
    const btnText = document.getElementById("url-btn-text");
    const fetchBtn = document.getElementById("btn-fetch-url");
    const rangeBox = document.getElementById("url-range-extractor-box");

    spinner.classList.remove("hidden");
    btnText.textContent = "Đang quét metadata...";
    fetchBtn.disabled = true;

    try {
        // Giai đoạn 1: Quét Metadata nhanh trong 0.5s
        const probeRes = await fetch("/api/video/probe_url", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url })
        });
        const probe = await probeRes.json();
        if (probe.status !== "success") {
            showToast("Không thể đọc video từ liên kết: " + (probe.detail || JSON.stringify(probe)), "error");
            return;
        }

        currentProbedURLData = probe;
        currentProbedURLData.url = url;

        // Nếu video ngắn (<= 180s = 3 phút): Tải trực tiếp toàn bộ
        if (!probe.is_long) {
            if (rangeBox) rangeBox.classList.add("hidden");
            const estDlSec = Math.max(2, Math.round((probe.duration || 30) / 15 + 2));
            btnText.textContent = `Đang tải video (Dự kiến: ~${estDlSec}s)...`;
            const res = await fetch("/api/video/import_url", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url })
            });
            const data = await res.json();
            if (data.status === "success") {
                loadVideoIntoTrimmer(data);
            } else {
                showToast("Lỗi tải video từ URL: " + (data.detail || JSON.stringify(data)), "error");
            }
        } else {
            // Nếu video dài (> 180s): Mở Hộp thoại Smart Range Extractor cho người dùng chọn dải bất kỳ
            if (rangeBox) {
                rangeBox.classList.remove("hidden");
                safeSetText("url-meta-title", probe.title || "Video từ Internet");
                safeSetText("url-meta-duration", `Thời lượng: ${probe.duration_str || formatTime(probe.duration)}`);
                const thumbEl = document.getElementById("url-meta-thumb");
                if (thumbEl && probe.thumbnail) {
                    thumbEl.src = probe.thumbnail;
                }

                // Thiết lập mốc mặc định (00:00 -> 01:30) hoặc tự động phát hiện ?t=... từ URL
                const sInput = document.getElementById("url-slice-start");
                const eInput = document.getElementById("url-slice-end");
                const tMatch = url.match(/[?&]t=(\d+)s?/);
                if (tMatch) {
                    const startT = parseInt(tMatch[1]);
                    const endT = Math.min(startT + 30, probe.duration || (startT + 30));
                    if (sInput) sInput.value = formatTime(startT);
                    if (eInput) eInput.value = formatTime(endT);
                } else {
                    if (sInput) sInput.value = "00:00";
                    if (eInput) eInput.value = "01:30";
                }

                // Tạo các nút Preset mốc nhanh theo thời lượng video
                const presetsContainer = document.getElementById("url-slice-presets");
                if (presetsContainer) {
                    presetsContainer.innerHTML = `<span class="preset-label">Mốc nhanh:</span>`;
                    const dur = probe.duration;
                    const candidates = [
                        { label: "00:00 — 01:30", s: 0, e: 90 }
                    ];
                    if (dur >= 300) candidates.push({ label: "05:00 — 06:30", s: 300, e: 390 });
                    if (dur >= 600) candidates.push({ label: "10:00 — 11:30", s: 600, e: 690 });
                    if (dur >= 900) candidates.push({ label: "15:00 — 16:30", s: 900, e: 990 });
                    if (dur >= 1800) candidates.push({ label: "30:00 — 31:30", s: 1800, e: 1890 });

                    candidates.forEach(c => {
                        const btn = document.createElement("button");
                        btn.className = "preset-chip";
                        btn.textContent = c.label;
                        btn.onclick = () => setSlicePreset(c.s, c.e);
                        presetsContainer.appendChild(btn);
                    });
                }

                rangeBox.scrollIntoView({ behavior: 'smooth' });
            }
        }
    } catch (e) {
        alert("Lỗi kết nối khi quét URL: " + e);
    } finally {
        spinner.classList.add("hidden");
        btnText.innerHTML = `${ICONS.search}<span>Kiểm Tra & Nạp Video</span>`;
        fetchBtn.disabled = false;
    }
}

// Xác nhận tải đúng phân đoạn start_time -> end_time bằng HTTP Byte Ranges
async function confirmURLRangeExtract() {
    if (!currentProbedURLData || !currentProbedURLData.url) {
        alert("Vui lòng quét thông tin video trước.");
        return;
    }

    const sStr = document.getElementById("url-slice-start").value;
    const eStr = document.getElementById("url-slice-end").value;

    const startSec = parseTimeToSeconds(sStr);
    let endSec = parseTimeToSeconds(eStr);

    if (endSec <= startSec) {
        alert("Mốc thời gian kết thúc phải lớn hơn mốc bắt đầu.");
        return;
    }

    // Giới hạn dải tối đa 90 giây
    if (endSec - startSec > 90.0) {
        endSec = startSec + 90.0;
        document.getElementById("url-slice-end").value = formatTime(endSec);
        alert("Để tối ưu tốc độ tải và đảm bảo hiệu năng GPU, hệ thống đã tự động giới hạn độ dài phân đoạn là 90 giây.");
    }

    const spinner = document.getElementById("url-slice-spinner");
    const btnText = document.getElementById("url-slice-text");
    const confirmBtn = document.getElementById("btn-confirm-slice");

    const sliceDur = Math.max(1, endSec - startSec);
    const estSliceSec = Math.max(2, Math.round(sliceDur / 18 + 2));
    spinner.classList.remove("hidden");
    btnText.textContent = `Đang trích xuất ${formatTime(startSec)} — ${formatTime(endSec)} (Dự kiến: ~${estSliceSec}s)...`;
    confirmBtn.disabled = true;

    try {
        const res = await fetch("/api/video/import_url", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                url: currentProbedURLData.url,
                start_time: startSec,
                end_time: endSec
            })
        });
        const data = await res.json();
        if (data.status === "success") {
            const rangeBox = document.getElementById("url-range-extractor-box");
            if (rangeBox) rangeBox.classList.add("hidden");
            loadVideoIntoTrimmer(data);
        } else {
            showToast("Lỗi trích xuất phân đoạn URL: " + (data.detail || JSON.stringify(data)), "error");
        }
    } catch (e) {
        showToast("Lỗi kết nối khi trích xuất phân đoạn URL: " + e, "error");
    } finally {
        spinner.classList.add("hidden");
        btnText.innerHTML = `${ICONS.zap}<span>Tải Phân Đoạn Vào Timeline</span>`;
        confirmBtn.disabled = false;
    }
}

// ==============================================================================
// CAPCUT-STYLE TIMELINE TRIMMER
// ==============================================================================
function loadVideoIntoTrimmer(videoData) {
    currentVideoData = videoData;
    const timelineSec = document.getElementById("timeline-section");
    timelineSec.classList.remove("hidden");

    // Hide old results if any
    document.getElementById("results-section").classList.add("hidden");
    document.getElementById("processing-section").classList.add("hidden");

    const previewVid = document.getElementById("preview-video");
    const previewEmpty = document.getElementById("preview-empty-state");
    if (previewEmpty) previewEmpty.classList.add("hidden");
    if (previewVid) {
        previewVid.classList.remove("hidden");
        previewVid.src = videoData.stream_url;
        previewVid.load();

        previewVid.onloadedmetadata = () => {
            const dur = previewVid.duration || videoData.duration || 60;
            initSliders(dur);
        };

        previewVid.onerror = () => {
            if (previewEmpty) previewEmpty.classList.remove("hidden");
        };
    }

    // Scroll to timeline section smoothly
    timelineSec.scrollIntoView({ behavior: 'smooth' });
}

function initSliders(duration) {
    const rangeStart = document.getElementById("range-start");
    const rangeEnd = document.getElementById("range-end");
    const rulerMid = document.getElementById("ruler-mid");
    const rulerEnd = document.getElementById("ruler-end");

    rangeStart.min = 0;
    rangeStart.max = duration;
    rangeStart.step = 0.1;
    rangeStart.value = 0;

    rangeEnd.min = 0;
    rangeEnd.max = duration;
    rangeEnd.step = 0.1;
    // Default selection: min(60s, duration)
    rangeEnd.value = Math.min(60.0, duration);

    rulerMid.textContent = formatTime(duration / 2);
    rulerEnd.textContent = formatTime(duration);

    // Populate filmstrip ticks (DaVinci / CapCut style)
    const ticksContainer = document.getElementById("timeline-ticks");
    if (ticksContainer) {
        ticksContainer.innerHTML = "";
        const totalTicks = 24;
        for (let i = 0; i <= totalTicks; i++) {
            const tick = document.createElement("div");
            tick.className = (i % 4 === 0) ? "timeline-tick tick-major" : "timeline-tick";
            ticksContainer.appendChild(tick);
        }
    }

    updateTimelineReadout();
}

function onRangeStartChange(val) {
    const rangeStart = document.getElementById("range-start");
    const rangeEnd = document.getElementById("range-end");
    let startVal = parseFloat(val);
    let endVal = parseFloat(rangeEnd.value);

    if (startVal >= endVal - 1.0) {
        startVal = Math.max(0, endVal - 1.0);
        rangeStart.value = startVal;
    }

    // Seek video preview to start frame (like CapCut)
    const previewVid = document.getElementById("preview-video");
    previewVid.currentTime = startVal;

    updateTimelineReadout();
}

function onRangeEndChange(val) {
    const rangeStart = document.getElementById("range-start");
    const rangeEnd = document.getElementById("range-end");
    let startVal = parseFloat(rangeStart.value);
    let endVal = parseFloat(val);

    if (endVal <= startVal + 1.0) {
        endVal = startVal + 1.0;
        rangeEnd.value = endVal;
    }

    // Seek video preview to end frame
    const previewVid = document.getElementById("preview-video");
    previewVid.currentTime = endVal;

    updateTimelineReadout();
}

function applyPreset(preset) {
    if (!currentVideoData) return;
    const previewVid = document.getElementById("preview-video");
    const totalDur = previewVid.duration || currentVideoData.duration || 60;
    const rangeStart = document.getElementById("range-start");
    const rangeEnd = document.getElementById("range-end");

    rangeStart.value = 0;
    if (preset === 'all') {
        rangeEnd.value = totalDur;
    } else {
        rangeEnd.value = Math.min(parseFloat(preset), totalDur);
    }
    updateTimelineReadout();
}

function updateTimelineReadout() {
    const rangeStart = document.getElementById("range-start");
    const rangeEnd = document.getElementById("range-end");
    if (!rangeStart || !rangeEnd) return;

    const startVal = parseFloat(rangeStart.value) || 0;
    const endVal = parseFloat(rangeEnd.value) || 0;
    const selDuration = Math.max(0.1, endVal - startVal);
    const maxVal = parseFloat(rangeStart.max) || 1.0;

    const startDisp = document.getElementById("trim-start-display");
    const endDisp = document.getElementById("trim-end-display");
    const durDisp = document.getElementById("trim-duration-display");
    if (startDisp) startDisp.textContent = formatTime(startVal);
    if (endDisp) endDisp.textContent = formatTime(endVal);
    if (durDisp) durDisp.textContent = `${selDuration.toFixed(1)} giây`;

    // Update highlight region on timeline rail (CapCut / DaVinci Resolve)
    const trimHighlight = document.getElementById("timeline-trim-highlight");
    if (trimHighlight && maxVal > 0) {
        const startPct = Math.max(0, Math.min(100, (startVal / maxVal) * 100));
        const endPct = Math.max(0, Math.min(100, (endVal / maxVal) * 100));
        trimHighlight.style.left = `${startPct}%`;
        trimHighlight.style.width = `${Math.max(0, endPct - startPct)}%`;
    }

    // Token Guard Meter logic & Dynamic Processing Time Estimate
    const estFrames = Math.max(25, Math.round(selDuration * 25));
    const estSec = Math.max(5, Math.round(estFrames / 42 + 4));
    const estTimeLabel = estSec >= 60
        ? `~${Math.floor(estSec / 60)}p ${estSec % 60}s`
        : `~${estSec} giây`;

    const meterBadge = document.getElementById("token-meter");
    if (meterBadge) {
        if (selDuration <= 60.0) {
            meterBadge.className = "token-meter-badge";
            meterBadge.innerHTML = `<span class="meter-dot dot-safe"></span><span>TỐI ƯU HOÀN HẢO — Dự kiến xử lý ${estTimeLabel}, &lt;1,200 tokens</span>`;
        } else if (selDuration <= 90.0) {
            meterBadge.className = "token-meter-badge warning";
            meterBadge.innerHTML = `<span class="meter-dot dot-warn"></span><span>ĐẠT TIÊU CHUẨN — Dự kiến xử lý ${estTimeLabel}, ~1,500 tokens</span>`;
        } else {
            meterBadge.className = "token-meter-badge danger";
            meterBadge.innerHTML = `<span class="meter-dot dot-danger"></span><span>THỜI LƯỢNG DÀI — Dự kiến xử lý ${estTimeLabel}</span>`;
        }
    }
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

function formatEtaSeconds(secVal) {
    const s = Math.max(1, Math.round(secVal));
    if (s >= 60) {
        const m = Math.floor(s / 60);
        const rem = s % 60;
        return `${m} phút ${rem.toString().padStart(2, '0')} giây`;
    }
    return `~${s} giây`;
}

let jobStartTime = 0;
let smoothedJobFps = 0;

// ==============================================================================
// STEP 3: LAUNCH PROCESSING & MONITOR JOB
// ==============================================================================
async function launchProcessing() {
    if (!currentVideoData) {
        alert("Vui lòng tải hoặc nạp video trước.");
        return;
    }

    const startVal = parseFloat(document.getElementById("range-start").value);
    const endVal = parseFloat(document.getElementById("range-end").value);
    const chkAnomaly = document.getElementById("chk-anomaly-focus");
    const anomalyFocus = chkAnomaly ? chkAnomaly.checked : true;

    const payload = {
        video_path: currentVideoData.video_path,
        start_time: startVal,
        end_time: endVal,
        call_gemini: true,
        anomaly_focus: anomalyFocus
    };

    jobStartTime = Date.now();
    smoothedJobFps = 0;
    const clipDur = Math.max(1, endVal - startVal);
    const initEstSec = Math.max(5, Math.round((clipDur * 25) / 42 + 4));

    // Show processing section
    const procSec = document.getElementById("processing-section");
    procSec.classList.remove("hidden");
    document.getElementById("results-section").classList.add("hidden");
    safeSetText("proc-eta-badge", `Dự kiến còn: ${formatEtaSeconds(initEstSec)}`);
    safeSetText("proc-eta-detail", `Đã chạy: 0 giây • Dự kiến hoàn tất sau: ${formatEtaSeconds(initEstSec)}`);
    procSec.scrollIntoView({ behavior: 'smooth' });

    try {
        const res = await fetch("/api/video/process", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        currentJobId = data.job_id;

        // Start polling progress
        if (jobPollInterval) clearInterval(jobPollInterval);
        jobPollInterval = setInterval(pollJobProgress, 500);

    } catch (e) {
        alert("Lỗi khởi chạy xử lý: " + e);
    }
}

async function pollJobProgress() {
    if (!currentJobId) return;

    try {
        const res = await fetch(`/api/video/job/${currentJobId}`);
        if (!res.ok) return;
        const job = await res.json();

        if (job.status === "processing") {
            const rawPct = job.progress_percent || 0;
            // STRICT GUARANTEE: Never show 100% while still processing.
            // When still running background tasks, cap strictly at 99%.
            const pct = Math.min(99, Math.floor(rawPct));
            const progressFill = document.getElementById("proc-progress-fill");
            if (progressFill) progressFill.style.width = `${pct}%`;
            const pctText = document.getElementById("proc-pct-text");
            if (pctText) pctText.textContent = `${pct}%`;
            const framesText = document.getElementById("proc-frames-text");
            if (framesText) {
                const stageStr = job.stage ? ` • ${job.stage}` : '';
                framesText.textContent = `Khung hình: ${job.current_frame} / ${job.total_frames}${stageStr}`;
            }
            const fpsBadge = document.getElementById("proc-fps-badge");
            if (fpsBadge && job.current_fps != null) {
                fpsBadge.textContent = `${job.current_fps} FPS`;
            }

            // Calculate live elapsed time & smoothed ETA
            const elapsedSec = jobStartTime > 0 ? Math.max(0, Math.round((Date.now() - jobStartTime) / 1000)) : 0;
            const curFps = parseFloat(job.current_fps || 0);
            if (curFps > 1.0) {
                smoothedJobFps = smoothedJobFps > 0 ? (0.7 * smoothedJobFps + 0.3 * curFps) : curFps;
            }
            const effFps = smoothedJobFps > 1.0 ? smoothedJobFps : 38.0;
            const totalFrames = parseInt(job.total_frames || 0, 10);
            const curFrame = parseInt(job.current_frame || 0, 10);
            const stgLower = (job.stage || "").toLowerCase();

            let etaSec = 4;
            if (stgLower.includes("mã hóa") || stgLower.includes("đối sánh")) {
                etaSec = 2;
            } else if (stgLower.includes("hội chẩn")) {
                etaSec = 3;
            } else if (totalFrames > 0 && curFrame < totalFrames) {
                const remFrames = Math.max(0, totalFrames - curFrame);
                etaSec = (remFrames / effFps) + 4.0;
            } else if (pct > 3 && elapsedSec > 1) {
                etaSec = Math.max(2, ((100 - pct) / pct) * elapsedSec);
            }

            const etaFormatted = formatEtaSeconds(etaSec);
            safeSetText("proc-eta-badge", `Dự kiến còn: ${etaFormatted}`);
            safeSetText("proc-eta-detail", `Đã chạy: ${elapsedSec} giây • Dự kiến hoàn tất sau: ${etaFormatted}`);

            // Live 3-Stage OS Pipeline Strip Telemetry
            const pl = job.pipeline_live || {};
            const totalF = job.total_frames || 0;
            const curF = job.current_frame || 0;
            const readerF = pl.reader_frames != null ? pl.reader_frames : curF;
            const inferF = pl.infer_frames != null ? pl.infer_frames : curF;
            const writerF = pl.writer_frames != null ? pl.writer_frames : curF;
            const rawQ = pl.raw_q != null ? pl.raw_q : 0;
            const writerQ = pl.writer_q != null ? pl.writer_q : 0;
            const qMax = pl.q_max || 16;
            const stride = pl.infer_stride || 1;

            safeSetText("pipe-live-reader", totalF > 0 ? `Đọc: ${readerF} / ${totalF}` : "Đang khởi tạo...");
            safeSetText("pipe-live-rawbuf", `Hàng đợi: ${rawQ} / ${qMax}`);
            if (stgLower.includes("hội chẩn")) {
                safeSetText("pipe-live-infer", "Gemini Multimodal AI");
            } else if (stgLower.includes("mã hóa") || stgLower.includes("đối sánh")) {
                safeSetText("pipe-live-infer", `Hoàn tất ${inferF} frames`);
            } else {
                const strideTag = stride > 1 ? ` · Stride ${stride}x` : "";
                safeSetText("pipe-live-infer", `GPU: ${job.current_fps || 0} FPS${strideTag}`);
            }
            safeSetText("pipe-live-writerbuf", `Hàng đợi: ${writerQ} / ${qMax}`);
            if (stgLower.includes("mã hóa")) {
                safeSetText("pipe-live-writer", "FFmpeg H.264 Encoding...");
            } else {
                safeSetText("pipe-live-writer", `Ghi: ${writerF} / ${totalF}`);
            }

            const rawPill = document.getElementById("pipe-pill-rawbuf");
            const wrPill = document.getElementById("pipe-pill-writerbuf");
            if (rawPill) rawPill.classList.toggle("buf-active", rawQ > 0);
            if (wrPill) wrPill.classList.toggle("buf-active", writerQ > 0);

            updateLivePipelineModal({
                is_completed: false,
                progress_pct: pct,
                current_frame: curF,
                total_frames: totalF,
                current_fps: job.current_fps || Number(effFps.toFixed(1)),
                ms_per_frame: pl.ms_per_frame || (effFps > 0 ? Number((1000 / effFps).toFixed(1)) : 32.0),
                raw_q: rawQ,
                writer_q: writerQ,
                q_max: qMax,
                mutex_locks: pl.mutex_locks || 0,
                cond_waits: pl.cond_waits || 0,
                cond_signals: pl.cond_signals || 0,
                frame_deck: pl.frame_deck || [],
                trace_logs: pl.trace_logs || [],
                stage: job.stage || ""
            });
        } else if (job.status === "completed") {
            clearInterval(jobPollInterval);
            const totalElapsed = jobStartTime > 0 ? Math.max(1, Math.round((Date.now() - jobStartTime) / 1000)) : 0;
            const progressFill = document.getElementById("proc-progress-fill");
            if (progressFill) progressFill.style.width = `100%`;
            const pctText = document.getElementById("proc-pct-text");
            if (pctText) pctText.textContent = `100%`;
            safeSetText("proc-eta-badge", `Hoàn tất · ${totalElapsed}s`);
            safeSetText("proc-eta-detail", `Tổng thời gian thực thi: ${totalElapsed} giây • Đã hoàn tất 100%`);
            const framesText = document.getElementById("proc-frames-text");
            if (framesText) framesText.textContent = "Hoàn tất phân tích 100% — Đang hiển thị kết quả...";

            if (job.result && job.result.os_pipeline_report) {
                const osRep = job.result.os_pipeline_report;
                const b1 = osRep.raw_buffer || {};
                const b2 = osRep.writer_buffer || {};
                const st2 = osRep.stage2_inference || {};
                const fFps = Number(st2.throughput_fps || job.result.overall_fps || 30.0);
                updateLivePipelineModal({
                    is_completed: true,
                    progress_pct: 100,
                    current_frame: job.result.total_frames || 0,
                    total_frames: job.result.total_frames || 0,
                    current_fps: fFps,
                    ms_per_frame: fFps > 0 ? Number((1000 / fFps).toFixed(1)) : 28.0,
                    raw_q: b1.high_water_mark || 0,
                    writer_q: b2.high_water_mark || 0,
                    q_max: b1.capacity || 16,
                    mutex_locks: osRep.total_mutex_locks || 0,
                    cond_waits: osRep.total_condition_waits || 0,
                    cond_signals: osRep.total_condition_signals || 0,
                    frame_deck: osRep.final_frame_deck || [],
                    trace_logs: osRep.final_trace_logs || []
                });
            }

            // Immediate transition: no waiting! (Note: #os-live-pipeline-modal stays open if user has it open)
            setTimeout(() => {
                document.getElementById("processing-section").classList.add("hidden");
                renderResults(job.result);
            }, 80);
        } else if (job.status === "error") {
            clearInterval(jobPollInterval);
            alert("Lỗi trong quá trình xử lý AI: " + job.error);
            document.getElementById("processing-section").classList.add("hidden");
        }
    } catch (e) {
        console.error("Poll job error:", e);
    }
}

// ==============================================================================
// STEP 4: RENDER RESULTS & SEMANTIC Q&A
// ==============================================================================
function renderResults(result) {
    const resSec = document.getElementById("results-section");
    resSec.classList.remove("hidden");
    resSec.scrollIntoView({ behavior: 'smooth' });

    // Store state
    currentAnalysisResult = result;
    currentSegments = result.timeline_segments || [];
    currentHeatmapData = result.heatmap_data || [];
    allEntitiesDetected = result.entities_detected || [];
    activeFocusSegment = null;
    isLoopingSegment = false;
    activeEntityFilter = 'all';
    currentResultDuration = result.duration_seconds || 30.0;

    // Video Players
    const origVid = document.getElementById("result-orig-video");
    const annotVid = document.getElementById("result-annotated-video");
    origVid.src = result.raw_trimmed_stream_url || currentVideoData.stream_url;
    annotVid.src = result.annotated_stream_url;

    // Download Button
    const dlBtn = document.getElementById("btn-download-mp4");
    if (dlBtn) dlBtn.href = result.download_url;

    // Gemini Synthesis Report
    const gemini = result.gemini_report || {};
    const threatBadge = document.getElementById("rep-threat-level");
    const threatLevel = gemini.threat_level || result.overall_danger_level || "AN TOÀN";
    const maxScore = parseFloat(result.max_danger_score || 0);

    const isGeminiSafe = (
        gemini.threat_level === "AN TOÀN" ||
        gemini.threat_level === "SAFE" ||
        gemini.is_safe_environment === true ||
        result.overall_danger_level === "AN TOAN" ||
        result.overall_danger_level === "AN TOÀN"
    );

    if (!isGeminiSafe && (threatLevel.includes("NGUY") || threatLevel.includes("DANGER") || maxScore >= 8.0)) {
        threatBadge.className = "badge badge-danger";
        threatBadge.style.color = "";
        threatBadge.textContent = "NGUY HIỂM";
    } else if (!isGeminiSafe && (threatLevel.includes("CANH") || threatLevel.includes("WARNING") || maxScore >= 4.0)) {
        threatBadge.className = "badge badge-warning";
        threatBadge.style.color = "";
        threatBadge.textContent = "CẢNH BÁO";
    } else {
        threatBadge.className = "badge badge-safe";
        threatBadge.style.color = "";
        threatBadge.textContent = "AN TOÀN";
    }

    safeSetText("rep-primary-incident", gemini.primary_incident || result.peak_danger_reason || "Bình thường");
    safeSetText("rep-diagnosis", gemini.detailed_diagnosis || "Không ghi nhận dấu hiệu thương tích hoặc bạo lực bất thường.");
    safeSetText("rep-recommendation", gemini.recommended_action || "Duy trì chế độ giám sát tự động thông thường.");
    safeSetText("report-token-badge", `Tiêu thụ: ~${gemini.token_usage || 1120} Tokens`);

    // Action Percentages
    const barsContainer = document.getElementById("action-bars-container");
    if (barsContainer) {
        barsContainer.innerHTML = "";
        const pcts = result.action_percentages || {};
        for (const [action, pct] of Object.entries(pcts)) {
            const item = document.createElement("div");
            item.className = "bar-item";
            item.innerHTML = `
                <div class="bar-labels">
                    <span>${escapeHtml(action)}</span>
                    <span class="mono">${pct}%</span>
                </div>
                <div class="bar-track">
                    <div class="bar-fill" style="width: ${pct}%;"></div>
                </div>
            `;
            barsContainer.appendChild(item);
        }
    }

    // Timeline Events (Legacy container if present)
    const tlContainer = document.getElementById("timeline-events-container");
    if (tlContainer) {
        tlContainer.innerHTML = "";
        const events = result.timeline || [];
        if (events.length === 0) {
            tlContainer.innerHTML = `<div class="timeline-entry"><span class="timeline-event">Toàn bộ đoạn video an toàn, không có sự cố.</span></div>`;
        } else {
            events.forEach(ev => {
                const entry = document.createElement("div");
                entry.className = "timeline-entry";
                entry.innerHTML = `
                    <span class="timeline-time mono">[${escapeHtml(ev.time)}]</span>
                    <span class="timeline-event">${escapeHtml(ev.event)}</span>
                    <span class="badge ${ev.severity && ev.severity.includes('NGUY') ? 'badge-danger' : 'badge-safe'}">${escapeHtml(ev.severity)}</span>
                `;
                tlContainer.appendChild(entry);
            });
        }
    }

    // Set up Synchronized Video Players & Looping
    setupDualPlayerSync();

    // Render Timeline Heatmap Bar
    renderHeatmap(currentHeatmapData, currentResultDuration);

    // Render Entity Filters
    renderEntityFilters(allEntitiesDetected, result);

    // Render Timeline Segments Master Table
    renderTimelineSegments();

    // Render 3-Stage OS Pipeline Execution Report
    renderOSPipelineReport(result.os_pipeline_report, result);

    // Render Executive Scene Narrative & Chronological Evolution
    renderExecutiveSceneNarrative(result);

    // Render Multi-dimensional Behavior & Risk Analytics Dashboard
    renderBehaviorAnalytics(result.behavior_analytics, currentResultDuration);
}

// ==============================================================================
// DUAL VIDEO PLAYERS SYNCHRONIZATION & HEATMAP PLAYHEAD
// ==============================================================================
function setupDualPlayerSync() {
    const origVid = document.getElementById("result-orig-video");
    const annotVid = document.getElementById("result-annotated-video");
    if (!origVid || !annotVid) return;

    let isSyncing = false;

    function syncEvent(source, target) {
        if (isSyncing) return;
        isSyncing = true;
        if (Math.abs(source.currentTime - target.currentTime) > 0.15) {
            target.currentTime = source.currentTime;
        }
        if (!source.paused && target.paused) {
            target.play().catch(() => {});
        } else if (source.paused && !target.paused) {
            target.pause();
        }
        setTimeout(() => { isSyncing = false; }, 40);
    }

    origVid.onplay = () => syncEvent(origVid, annotVid);
    origVid.onpause = () => syncEvent(origVid, annotVid);
    origVid.onseeked = () => syncEvent(origVid, annotVid);

    annotVid.onplay = () => syncEvent(annotVid, origVid);
    annotVid.onpause = () => syncEvent(annotVid, origVid);
    annotVid.onseeked = () => syncEvent(annotVid, origVid);

    annotVid.ontimeupdate = () => {
        const curT = annotVid.currentTime;

        // Sync origVid playhead if drift > 0.25s
        if (!isSyncing && Math.abs(origVid.currentTime - curT) > 0.25) {
            origVid.currentTime = curT;
        }

        // Loop / pause at segment boundary if focused
        if (activeFocusSegment) {
            if (curT >= activeFocusSegment.end_sec) {
                if (isLoopingSegment) {
                    annotVid.currentTime = activeFocusSegment.start_sec;
                    origVid.currentTime = activeFocusSegment.start_sec;
                    annotVid.play().catch(() => {});
                } else {
                    annotVid.pause();
                    origVid.pause();
                }
            }
        }

        updateHeatmapPlayhead(curT);
        updateChartPlayhead(curT, currentResultDuration);
        updateEventFlowPlayhead(curT);
    };
}

let lastScrollOriginElement = null;
let lastScrollOriginLabel = "";
let isSmoothScrollingToPlayer = false;

function showScrollBackAssistant(originElement, label = "") {
    lastScrollOriginElement = originElement;
    lastScrollOriginLabel = label;
    const btn = document.getElementById("floating-scroll-back-btn");
    const labelEl = document.getElementById("scroll-back-label");
    const quickBtn = document.getElementById("btn-quick-scroll-back");
    const quickLabelEl = document.getElementById("btn-quick-scroll-back-text");

    const displayText = label ? `Quay lại: ${label}` : "Quay lại Phân Đoạn";
    if (labelEl) labelEl.textContent = displayText;
    if (quickLabelEl) quickLabelEl.textContent = displayText;

    if (btn) {
        btn.classList.remove("hidden");
        void btn.offsetWidth;
        btn.classList.add("visible");
    }
    if (quickBtn) {
        quickBtn.classList.remove("hidden");
    }
}

function hideScrollBackAssistant() {
    const btn = document.getElementById("floating-scroll-back-btn");
    const quickBtn = document.getElementById("btn-quick-scroll-back");
    if (btn) {
        btn.classList.remove("visible");
        setTimeout(() => {
            if (!btn.classList.contains("visible")) {
                btn.classList.add("hidden");
            }
        }, 280);
    }
    if (quickBtn) {
        quickBtn.classList.add("hidden");
    }
}

function scrollToLastOrigin() {
    if (lastScrollOriginElement) {
        lastScrollOriginElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        lastScrollOriginElement.classList.add("highlight-pulse");
        setTimeout(() => {
            if (lastScrollOriginElement) lastScrollOriginElement.classList.remove("highlight-pulse");
        }, 2500);
    }
    hideScrollBackAssistant();
}

window.addEventListener("scroll", () => {
    // Không tự động ẩn nếu đang trong quá trình cuộn mượt lên player
    if (isSmoothScrollingToPlayer) return;
    if (!lastScrollOriginElement) return;
    const btn = document.getElementById("floating-scroll-back-btn");
    if (!btn || !btn.classList.contains("visible")) return;
    const rect = lastScrollOriginElement.getBoundingClientRect();
    // Chỉ ẩn khi người dùng đã tự cuộn màn hình xuống vùng phần tử gốc (trong phạm vi tầm nhìn)
    const windowH = window.innerHeight || document.documentElement.clientHeight;
    if (rect.top >= 60 && rect.bottom <= windowH - 60) {
        hideScrollBackAssistant();
    }
}, { passive: true });

function seekBothPlayers(seconds, autoPlay = false, originEl = null, originLabel = "") {
    const origVid = document.getElementById("result-orig-video");
    const annotVid = document.getElementById("result-annotated-video");
    const wasPlaying = (annotVid && !annotVid.paused) || (origVid && !origVid.paused);
    
    if (origVid) origVid.currentTime = seconds;
    if (annotVid) {
        annotVid.currentTime = seconds;
        if (autoPlay || wasPlaying) {
            annotVid.play().catch(() => {});
        }
    }
    
    // Cuộn màn hình mượt mà đến trình phát video để người dùng quan sát trực tiếp
    const playerSec = document.getElementById("result-annotated-video") || document.getElementById("result-orig-video");
    if (playerSec) {
        isSmoothScrollingToPlayer = true;
        playerSec.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setTimeout(() => {
            isSmoothScrollingToPlayer = false;
        }, 1500);
    }
    updateChartPlayhead(seconds, currentResultDuration);

    if (originEl) {
        showScrollBackAssistant(originEl, originLabel);
    }
}

// ==============================================================================
// TIMELINE HEATMAP BAR
// ==============================================================================
function renderHeatmap(heatmapData, totalDuration) {
    const container = document.getElementById("timeline-heatmap-bar");
    const axis = document.getElementById("heatmap-time-axis");
    if (!container) return;

    container.innerHTML = "";
    if (axis) axis.innerHTML = "";

    if (!heatmapData || heatmapData.length === 0) {
        container.innerHTML = `<div class="heatmap-cell safe" style="flex:1" title="00:00 - Bình thường"></div>`;
        return;
    }

    heatmapData.forEach((slot, idx) => {
        const cell = document.createElement("div");
        cell.className = `heatmap-cell ${slot.level || 'safe'}`;
        cell.dataset.time = slot.time;
        cell.dataset.idx = idx;
        cell.title = `[${slot.time_str}] Điểm đe dọa: ${slot.score} — ${(slot.level || 'safe').toUpperCase()} — Nhấn để tua`;
        cell.onclick = () => {
            seekBothPlayers(slot.time, false, cell, `Dòng [${slot.time_str}]`);
        };
        container.appendChild(cell);
    });

    if (axis) {
        const midTime = totalDuration / 2;
        axis.innerHTML = `
            <span>00:00</span>
            <span>${formatTime(midTime)}</span>
            <span>${formatTime(totalDuration)}</span>
        `;
    }

    if (typeof renderHeatmapZTrack === "function") {
        renderHeatmapZTrack(heatmapData, totalDuration);
    }
}

function updateHeatmapPlayhead(currentTime) {
    const cells = document.querySelectorAll(".heatmap-cell");
    if (!cells || cells.length === 0) return;

    cells.forEach(cell => {
        const t = parseFloat(cell.dataset.time || 0);
        if (Math.abs(t - currentTime) <= 0.4) {
            cell.classList.add("playing");
        } else {
            cell.classList.remove("playing");
        }
    });
}

// ==============================================================================
// ENTITY FILTERING & TIMELINE CHAPTERS TABLE
// ==============================================================================
function renderEntityFilters(entities, result) {
    const container = document.getElementById("entity-filter-container");
    if (!container) return;

    const res = result || currentAnalysisResult || {};
    const gemini = res.gemini_report || {};
    const isCrowd = Boolean(
        res.is_crowd_scene ||
        gemini.is_crowd_scene ||
        (res.actual_person_count > 4) ||
        (res.peak_concurrent_persons > 4)
    );

    if (isCrowd) {
        container.innerHTML = "";
        container.style.display = "none";
        activeEntityFilter = 'all';
        return;
    }

    container.style.display = "flex";
    container.innerHTML = `<span class="filter-label">Lọc đối tượng:</span>`;

    const allBtn = document.createElement("button");
    allBtn.className = `filter-chip ${activeEntityFilter === 'all' ? 'active' : ''}`;
    allBtn.id = "filter-chip-all";
    allBtn.textContent = `Tất cả — ${entities.length || 0}`;
    allBtn.onclick = () => filterByEntity('all');
    container.appendChild(allBtn);

    entities.forEach(entId => {
        const chip = document.createElement("button");
        chip.className = `filter-chip ${activeEntityFilter === entId ? 'active' : ''}`;
        chip.innerHTML = `${ICONS.user} <span>${escapeHtml(entId)}</span>`;
        chip.onclick = () => filterByEntity(entId);
        container.appendChild(chip);
    });
}

function filterByEntity(entId) {
    activeEntityFilter = entId;
    const chips = document.querySelectorAll("#entity-filter-container .filter-chip");
    chips.forEach(chip => {
        if (entId === 'all' && chip.textContent.includes('Tất cả')) {
            chip.classList.add("active");
        } else if (chip.textContent.includes(entId)) {
            chip.classList.add("active");
        } else {
            chip.classList.remove("active");
        }
    });

    renderTimelineSegments();
}

function renderTimelineSegments() {
    const tbody = document.getElementById("timeline-segments-tbody");
    if (!tbody) return;

    if (!currentSegments || currentSegments.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="5" class="empty-cell">
                    <div class="empty-state-box">
                        <span class="empty-icon">${ICONS.film}</span>
                        <p class="empty-title">Chưa có phân đoạn hành vi dòng thời gian</p>
                        <span class="empty-sub">Hãy tải video lên hoặc dán liên kết URL và nhấn "Xác nhận đoạn đã chọn & khởi động AI phân tích" để bắt đầu xử lý.</span>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    // Filter segments if activeEntityFilter !== 'all'
    const filtered = currentSegments.filter(seg => {
        if (activeEntityFilter === 'all') return true;
        return seg.entities && seg.entities.some(e => e.id === activeEntityFilter || (e.raw_id && activeEntityFilter.includes(e.raw_id)));
    });

    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="5" class="empty-cell">
                    <div class="empty-state-box">
                        <span class="empty-icon">${ICONS.filter}</span>
                        <p class="empty-title">Không tìm thấy phân đoạn phù hợp</p>
                        <span class="empty-sub">Không có phân đoạn xuất hiện đối tượng <strong>${escapeHtml(activeEntityFilter)}</strong>. Nhấn "Tất cả" để xem toàn bộ danh sách.</span>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    let html = "";
    filtered.forEach((seg) => {
        const isFocused = activeFocusSegment && activeFocusSegment.segment_id === seg.segment_id;
        const rowClass = isFocused ? "active-segment-row" : "";
        const numScore = parseFloat(seg.danger_score || 0);
        const isDanger = numScore >= 8.0 || seg.severity === "danger";
        const isWarn = (!isDanger && (numScore >= 4.0 || seg.severity === "warning"));
        const badgeClass = isDanger ? "badge badge-danger" : (isWarn ? "badge badge-warning" : "badge badge-safe");
        const badgeText = isDanger ? "NGUY HIỂM" : (isWarn ? "CẢNH BÁO" : "AN TOÀN");

        // Cột 3: Cơ sở đánh giá động học & đo đạc (tính trước để làm giàu ngữ cảnh nếu cần)
        const tb = seg.telemetry_breakdown;
        let breakdownHtml = "";
        let maxVelStr = "0 px/s";
        let minDistStr = "> 1.5 m";
        let dominantPosture = "Bình thường";
        if (tb) {
            const maxVelVal = tb.max_velocity !== undefined ? tb.max_velocity : (tb.strike_velocity || 0);
            maxVelStr = typeof maxVelVal === "number" ? `${maxVelVal} px/s` : String(maxVelVal);
            const minDistVal = tb.min_distance !== undefined ? tb.min_distance : (tb.proximity_dist || null);
            minDistStr = typeof minDistVal === "number" ? `${minDistVal} px` : (minDistVal ? String(minDistVal) : '> 1.5 m');
            dominantPosture = (tb.dominant_posture || tb.posture_state || 'Bình thường').replace(/[\(\)]/g, '').trim();

            breakdownHtml = `
                <div class="telemetry-breakdown-box">
                    <div class="tb-item" title="Vận tốc cử động tay/chân lớn nhất trong đoạn"><span class="tb-k">Vận tốc:</span> <strong class="tb-v mono">${escapeHtml(maxVelStr)}</strong></div>
                    <div class="tb-item" title="Khoảng cách tiếp cận gần nhất"><span class="tb-k">Tiếp cận:</span> <strong class="tb-v mono">${escapeHtml(minDistStr)}</strong></div>
                    <div class="tb-item" title="Tư thế phân đoạn"><span class="tb-k">Tư thế:</span> <span class="tb-v">${escapeHtml(dominantPosture)}</span></div>
                </div>
            `;
        }

        // Cột 2: Bên ngoài bảng chỉ hiển thị tóm tắt ngắn gọn + chip ID; chi tiết đầy đủ xem trong Modal Chi Tiết
        const summaryText = (seg.scene_summary || seg.context_description || "Khu vực sinh hoạt ổn định, không có xung đột.").trim();
        let rawDetailText = (seg.detailed_narrative || seg.context_description || "").trim();

        let actorChipsHtml = "";
        const entitySentenceParts = [];
        (seg.entities || []).forEach((ent, eIdx) => {
            if (!ent) return;
            const rawId = (ent.id !== null && ent.id !== undefined) ? String(ent.id) : "";
            if (rawId === "KHÔNG GIAN" || ent.raw_id === "ALL") return;
            const idMatch = rawId.match(/ID\s*#?(\d+)/i);
            const idTag = idMatch 
                ? `ID #${idMatch[1].padStart(2, '0')}` 
                : (ent.raw_id && String(ent.raw_id) !== "null" 
                    ? `ID #${String(ent.raw_id).padStart(2, '0')}` 
                    : (ent.canonical_id ? `ID #${String(ent.canonical_id).padStart(2, '0')}` : `ID #${String(eIdx + 1).padStart(2, '0')}`));
            
            const rawAnchor = (ent.distinctive_anchor || "").replace(/[\(\)\[\]]/g, '').trim();
            const rawLabel = ent.actor_label || ent.role || "";
            let actorName = rawAnchor || rawLabel || rawId.replace(/\(?ID\s*#?\d+\)?/i, '').replace(/[\(\)—-]/g, '').trim();
            if (actorName === "null" || actorName === "undefined" || /^(đối tượng|chủ thể|khu vực)\s*#?\d+/i.test(actorName)) {
                actorName = "";
            }

            const entAction = (ent.action || "").trim();
            const entPosture = (ent.posture || "").trim();
            const actionDisplay = entAction && entPosture && !entAction.toLowerCase().includes(entPosture.toLowerCase())
                ? `${entAction} (${entPosture.toLowerCase()})`
                : (entAction || entPosture);

            if (actionDisplay) {
                entitySentenceParts.push(`${idTag}${actorName ? ` (${actorName})` : ''}: ${actionDisplay.toLowerCase()}`);
            }

            const entBadgeClass = (isDanger && ent.severity === "danger")
                ? "tag-danger"
                : (((isDanger || isWarn) && (ent.severity === "warning" || ent.severity === "danger")) ? "tag-warning" : "tag-safe");

            actorChipsHtml += `
                <span class="seg-actor-chip ${entBadgeClass}" title="${escapeHtml(actionDisplay || actorName || idTag)}">
                    <span class="mono seg-chip-id">${idTag}</span>
                    ${actorName ? `<span class="seg-chip-name">${escapeHtml(actorName)}</span>` : ''}
                </span>
            `;
        });

        // Loại bỏ việc lặp lại câu tóm tắt trong đoạn chi tiết của Modal
        if (rawDetailText.length > summaryText.length && rawDetailText.startsWith(summaryText)) {
            rawDetailText = rawDetailText.slice(summaryText.length).replace(/^[\s.—-]+/, '').trim();
        }
        if (!rawDetailText || rawDetailText === summaryText) {
            if (entitySentenceParts.length > 0) {
                rawDetailText = `Trạng thái các đối tượng trên khung hình: ${entitySentenceParts.join("; ")}.`;
            } else {
                rawDetailText = summaryText;
            }
        }

        const predText = (seg.prediction_next_4s || "Duy trì trạng thái tương tác an toàn trong các giây tiếp theo").trim();
        const fullDescForModal = rawDetailText || summaryText;

        const summaryEscaped = escapeHtml(summaryText);
        const descEscaped = escapeHtml(fullDescForModal);
        const predEscaped = escapeHtml(predText);
        const snapThumb = seg.snapshot_url 
            ? `<img src="${escapeHtml(seg.snapshot_url)}" class="seg-snapshot-thumb" 
                onclick="openSnapshotModal('${escapeHtml(seg.snapshot_url)}', '${escapeHtml(seg.segment_id)}', '${summaryEscaped}', '${escapeHtml(seg.time_range)}', '${descEscaped}', '${predEscaped}')"
                title="Bấm để phóng to ảnh chụp kèm Bounding Box" />`
            : `<span class="mono text-muted">--</span>`;

        let weaponBadge = "";
        if (seg.weapon_detected) {
            weaponBadge = `<span class="badge badge-danger mono" style="margin-left: 6px; font-size: 0.78rem; background: var(--accent-crimson-bg); border: 1px solid var(--accent-crimson); color: var(--accent-crimson-text);">${ICONS.alertTriangle} ${escapeHtml(seg.weapon_detected)}</span>`;
        }

        const scoreVal = typeof seg.danger_score === 'number' ? seg.danger_score : parseFloat(seg.danger_score || 0);
        const scoreFormatted = (scoreVal || 0).toFixed(1);
        const threatPillClass = isDanger ? "threat-pill-danger" : (isWarn ? "threat-pill-warn" : "threat-pill-safe");

        html += `
            <tr class="${rowClass}" id="seg-row-${escapeHtml(seg.segment_id)}">
                <td>
                    <div class="seg-range-badge mono">${escapeHtml(seg.time_range)}</div>
                    <div class="seg-id-sub mono">${escapeHtml(seg.segment_id)}</div>
                </td>
                <td>
                    <div class="seg-summary-line">${escapeHtml(summaryText)}</div>
                    ${actorChipsHtml ? `<div class="seg-actors-compact-row">${actorChipsHtml}</div>` : ''}
                </td>
                <td>
                    <div class="threat-header-row">
                        <span class="${badgeClass}">${badgeText}</span>
                        ${weaponBadge}
                        <div class="threat-score-pill mono ${threatPillClass}">${scoreFormatted} <span class="threat-scale">/ 10</span></div>
                    </div>
                    ${breakdownHtml}
                </td>
                <td style="text-align: center;">
                    ${snapThumb}
                </td>
                <td style="text-align: right;">
                    <div class="seg-actions-group">
                        <button class="btn btn-sm btn-outline btn-detail-seg" 
                            onclick="openSegmentDetailModal('${escapeHtml(seg.segment_id)}')">
                            <svg class="ui-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg> <span>Chi Tiết</span>
                        </button>
                        <button class="btn btn-sm btn-primary btn-focus-seg" 
                            onclick="focusTimelineSegment(${seg.start_sec}, ${seg.end_sec}, '${escapeHtml(seg.segment_id)}', '${summaryEscaped}', this)">
                            ${ICONS.play} <span>Xem Đoạn</span>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

// ==============================================================================
// SEGMENT FOCUS & PLAYBACK LOOP MECHANICS
// ==============================================================================
function focusTimelineSegment(startSec, endSec, segId, summary, originBtn = null) {
    activeFocusSegment = {
        segment_id: segId,
        start_sec: parseFloat(startSec),
        end_sec: parseFloat(endSec),
        summary: summary
    };

    const banner = document.getElementById("segment-focus-banner");
    if (banner) {
        banner.classList.remove("hidden");
        safeSetText("focus-range-text", `${formatTime(startSec)} — ${formatTime(endSec)}`);
        safeSetText("focus-summary-text", summary || "Đang xem lại phân đoạn");
    }

    const rowEl = document.getElementById(`seg-row-${segId}`) || originBtn;
    seekBothPlayers(startSec, true, rowEl, segId);
    renderTimelineSegments();
}

function toggleLoopCurrentSegment() {
    isLoopingSegment = !isLoopingSegment;
    const btn = document.getElementById("btn-toggle-loop");
    if (btn) {
        btn.innerHTML = `${ICONS.repeat}<span>Lặp đoạn: ${isLoopingSegment ? "BẬT" : "TẮT"}</span>`;
        btn.className = isLoopingSegment ? "btn btn-xs btn-primary" : "btn btn-xs btn-outline";
    }
}

function clearSegmentFocus() {
    activeFocusSegment = null;
    isLoopingSegment = false;
    const banner = document.getElementById("segment-focus-banner");
    if (banner) banner.classList.add("hidden");
    const btn = document.getElementById("btn-toggle-loop");
    if (btn) {
        btn.innerHTML = `${ICONS.repeat}<span>Lặp đoạn: TẮT</span>`;
        btn.className = "btn btn-xs btn-outline";
    }
    renderTimelineSegments();
}

// Chatbot Q&A
async function sendChatMessage() {
    const input = document.getElementById("chat-question-input");
    if (!input) return;
    const question = input.value.trim();
    if (!question) return;

    const ansBox = document.getElementById("chat-answer-box");
    const ansText = document.getElementById("chat-answer-text");
    if (ansBox) ansBox.classList.remove("hidden");
    if (ansText) ansText.innerHTML = `<span class="spinner"></span> Đang truy vấn Gemini...`;

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, job_id: currentJobId })
        });
        const data = await res.json();
        if (ansText) ansText.textContent = data.answer || "Không nhận được phản hồi từ AI.";
    } catch (e) {
        if (ansText) ansText.textContent = "Lỗi kết nối khi hỏi đáp: " + e;
    }
}

// ==============================================================================
// STEP 5: EXECUTIVE SCENE NARRATIVE & CHRONOLOGICAL EVOLUTION
// ==============================================================================
function renderExecutiveSceneNarrative(result) {
    const card = document.getElementById("executive-scene-narrative-card");
    if (!card) return;

    const gemini = (result && result.gemini_report) ? result.gemini_report : {};
    const maxScore = parseFloat((result && result.max_danger_score) || 0);
    const threatLevel = gemini.threat_level || (result ? result.overall_danger_level : "AN TOÀN") || "AN TOÀN";
    const threatBadge = document.getElementById("narrative-threat-badge");
    if (threatBadge) {
        const isGeminiSafe = (
            gemini.threat_level === "AN TOÀN" ||
            gemini.threat_level === "SAFE" ||
            gemini.is_safe_environment === true ||
            (result && (result.overall_danger_level === "AN TOAN" || result.overall_danger_level === "AN TOÀN"))
        );

        if (!isGeminiSafe && (threatLevel.includes("NGUY") || threatLevel.includes("DANGER") || maxScore >= 8.0)) {
            threatBadge.className = "badge badge-danger mono";
            threatBadge.style.color = "";
            threatBadge.textContent = "NGUY HIỂM / KHẨN CẤP";
        } else if (!isGeminiSafe && (threatLevel.includes("CANH") || threatLevel.includes("WARNING") || threatLevel.includes("CẢNH") || maxScore >= 4.0)) {
            threatBadge.className = "badge badge-warning mono";
            threatBadge.style.color = "";
            threatBadge.textContent = "CẢNH BÁO";
        } else {
            threatBadge.className = "badge badge-safe mono";
            threatBadge.style.color = "";
            threatBadge.textContent = "AN TOÀN";
        }
    }

    // 1. Scene Context
    const sceneContext = gemini.scene_context || 
        `Khu vực sinh hoạt và vận động ổn định với ${result && result.entities_detected ? result.entities_detected.length : 1} đối tượng có mặt trong không gian.`;
    safeSetText("narrative-scene-context", sceneContext);

    // Actors Pills - 2-tier Card (Anti-slop, no bracket breaking)
    const actorsContainer = document.getElementById("narrative-actors-pills");
    if (actorsContainer) {
        actorsContainer.innerHTML = "";
        const isCrowd = Boolean(
            (result && result.is_crowd_scene) ||
            gemini.is_crowd_scene ||
            ((result && result.actual_person_count) > 4) ||
            ((result && result.peak_concurrent_persons) > 4)
        );

        if (isCrowd) {
            // Khi video có trên 4 người (cảnh đông người, lớp học):
            // Không hiển thị 4 thẻ ID cố định vì ID không cố định 1 người suốt video.
            // Thay vào đó hiển thị thẻ bối cảnh toàn cảnh đông người.
            const cardEl = document.createElement("div");
            cardEl.className = "actor-chip-card";
            cardEl.style.width = "100%";
            cardEl.innerHTML = `
                <div class="actor-chip-header">
                    <div class="actor-chip-identity">
                        <span class="actor-chip-id mono">BỐI CẢNH TOÀN CẢNH</span>
                        <span class="actor-chip-role">Không gian đông người (Nhiều cá nhân có mặt)</span>
                    </div>
                    <span class="actor-chip-anchor-badge">Cảnh đông người</span>
                </div>
                <div class="actor-chip-body">
                    Khu vực tập trung đông người với sự tham gia và luân chuyển của nhiều đối tượng. Các cá nhân và tương tác tiêu điểm được phân tích chi tiết theo từng phân đoạn độc lập trong bảng phân tích bên dưới.
                </div>
            `;
            actorsContainer.appendChild(cardEl);
        } else {
            const actors = gemini.detected_actors || [];
            if (actors.length > 0) {
                actors.forEach(act => {
                    const cardEl = document.createElement("div");
                    cardEl.className = "actor-chip-card";
                    const actorDisplay = act.actor_label || act.role || `Đối tượng #${act.actor_index}`;
                    const cleanAnchor = act.distinctive_anchor ? act.distinctive_anchor.replace(/^\[+|\]+$/g, '').trim() : '';
                    const anchorBadge = cleanAnchor ? `<span class="actor-chip-anchor-badge">${escapeHtml(cleanAnchor)}</span>` : '';
                    const actionText = act.true_action || act.posture_desc || 'Duy trì hoạt động ổn định trong phân cảnh.';
                    cardEl.innerHTML = `
                        <div class="actor-chip-header">
                            <div class="actor-chip-identity">
                                <span class="actor-chip-id mono">ID #${String(act.actor_index).padStart(2, '0')}</span>
                                <span class="actor-chip-role">${escapeHtml(actorDisplay)}</span>
                            </div>
                            ${anchorBadge}
                        </div>
                        <div class="actor-chip-body">
                            ${escapeHtml(actionText)}
                        </div>
                    `;
                    actorsContainer.appendChild(cardEl);
                });
            } else {
                const entities = (result && result.entities_detected) ? result.entities_detected : ["ID #01 — Chủ thể"];
                entities.forEach(ent => {
                    const cardEl = document.createElement("div");
                    cardEl.className = "actor-chip-card";
                    cardEl.innerHTML = `
                        <div class="actor-chip-header">
                            <div class="actor-chip-identity">
                                <span class="actor-chip-id mono">${escapeHtml(ent)}</span>
                            </div>
                            <span class="actor-chip-anchor-badge">Chủ thể</span>
                        </div>
                        <div class="actor-chip-body">
                            Duy trì tương tác an toàn, không có xung đột.
                        </div>
                    `;
                    actorsContainer.appendChild(cardEl);
                });
            }
        }
    }

    // 2. Chronological Evolution
    const chronoContainer = document.getElementById("narrative-chronology-flow");
    if (chronoContainer) {
        chronoContainer.innerHTML = "";
        let chronoText = gemini.chronological_evolution || "";
        
        let steps = [];
        if (chronoText.includes("Giai đoạn")) {
            const p1 = chronoText.match(/Giai đoạn (?:khởi )?đầu:?\s*([^.]+)/i);
            const p2 = chronoText.match(/Giai đoạn giữa:?\s*([^.]+)/i);
            const p3 = chronoText.match(/Giai đoạn kết(?: thúc)?:?\s*([^.]+)/i);
            steps = [
                { tag: "01. Khởi đầu", text: p1 ? p1[1].trim() + "." : "Bắt đầu quan sát: các đối tượng bước vào vị trí và phân vai." },
                { tag: "02. Diễn biến chính", text: p2 ? p2[1].trim() + "." : "Diễn biến chính: duy trì tương tác sinh hoạt nhịp nhàng, không có xung đột." },
                { tag: "03. Kết thúc", text: p3 ? p3[1].trim() + "." : "Kết thúc phân cảnh: toàn bộ đối tượng giữ vững thăng bằng và an toàn." }
            ];
        } else if (/(?:^|\n)\s*1[\s.:\-)—].+(?:\n|\s)2[\s.:\-)—]/s.test(chronoText)) {
            // Có từ 2 bước đánh số trở lên: phân tách theo các mốc
            const parts = chronoText.split(/(?:^|\n)\s*(?=[0-9]+[\s.:\-)—])/).filter(p => p && p.trim());
            parts.forEach((p, idx) => {
                const cleanP = p.replace(/^[0-9]+[\s.:\-)—]+/, '').trim();
                const tags = ["01. Khởi đầu", "02. Diễn biến chính", "03. Kết thúc"];
                const tag = idx < tags.length ? tags[idx] : `0${idx + 1}. Tiếp diễn`;
                steps.push({ tag: tag, text: cleanP });
            });
        } else if (chronoText) {
            // Chỉ có 1 phân đoạn: gọt sạch số 1 đơn độc nếu có ở đầu
            let cleanChrono = chronoText.replace(/^[0-9]+[\s.:\-)—]+/, '').trim();
            steps = [
                { tag: "Diễn biến toàn cảnh", text: cleanChrono }
            ];
        } else {
            steps = [
                { tag: "01. Khởi đầu", text: "Các đối tượng xuất hiện ổn định trong khung hình và thiết lập vị trí tương tác." },
                { tag: "02. Diễn biến chính", text: "Các cử chỉ vận động diễn ra điều độ, không có gia tốc va chạm hoặc té ngã." },
                { tag: "03. Kết thúc", text: "Trạng thái các thành viên ổn định và giữ vững thăng bằng hoàn toàn." }
            ];
        }

        steps.forEach(st => {
            const item = document.createElement("div");
            item.className = "chronology-step-item";
            item.innerHTML = `
                <span class="chronology-step-tag">${escapeHtml(st.tag)}</span>
                <span class="chronology-step-text">${escapeHtml(st.text)}</span>
            `;
            chronoContainer.appendChild(item);
        });
    }

    // 3. Conclusion & Recommendation
    const conclusionText = gemini.overall_conclusion || gemini.detailed_diagnosis || 
        "Toàn bộ chuỗi vận động và hoạt động của các đối tượng diễn ra an toàn, không phát hiện nguy cơ bất thường.";
    safeSetText("narrative-overall-conclusion", conclusionText);

    const recText = gemini.recommended_action || "Duy trì giám sát tự động theo chu kỳ.";
    safeSetText("narrative-recommendation-text", recText);
}

// ==============================================================================
// STEP 6: BEHAVIOR & RISK ANALYTICS DASHBOARD (NATIVE SVG)
// ==============================================================================
function renderBehaviorAnalytics(analytics, duration) {
    if (!analytics) {
        analytics = {
            risk_breakdown: { safe_pct: 95.0, warning_pct: 5.0, danger_pct: 0.0, dominant_risk: "safe" },
            posture_distribution: { upright_pct: 75.0, bent_pct: 20.0, slouched_pct: 5.0 },
            risk_curve: currentHeatmapData || [],
            ergonomic_score: 92,
            continuous_sitting_sec: 0,
            ergonomic_advice: "Tư thế sinh hoạt đạt mức Tốt. Trục cột sống duy trì góc độ giải phẫu học tự nhiên."
        };
    }

    duration = duration || (currentVideoData ? currentVideoData.duration : 30.0);
    const m = Math.floor(duration / 60);
    const s = Math.floor(duration % 60);
    safeSetText("analytics-duration-badge", `Thời lượng: ${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`);

    // 1. Donut 1: 3 Cấp Độ Nguy Hiểm
    const rb = analytics.risk_breakdown || {};
    const safeP = rb.safe_pct !== undefined ? rb.safe_pct : 95;
    const warnP = rb.warning_pct !== undefined ? rb.warning_pct : 5;
    const dangP = rb.danger_pct !== undefined ? rb.danger_pct : 0;

    safeSetText("legend-safe-val", `${safeP}%`);
    safeSetText("legend-warn-val", `${warnP}%`);
    safeSetText("legend-danger-val", `${dangP}%`);

    drawSvgDonut("svg-donut-risk", [
        { pct: safeP, color: "var(--accent-emerald)" },
        { pct: warnP, color: "var(--accent-amber)" },
        { pct: dangP, color: "var(--accent-crimson)" }
    ], rb.dominant_risk === "danger" ? "NGUY HIỂM" : (rb.dominant_risk === "warning" ? "CẢNH BÁO" : "AN TOÀN"));

    // 2. Donut 2: Phân Bổ Cột Sống (nếu có trong DOM)
    if (document.getElementById("svg-donut-posture")) {
        const pd = analytics.posture_distribution || {};
        const upP = pd.upright_pct !== undefined ? pd.upright_pct : 75;
        const bentP = pd.bent_pct !== undefined ? pd.bent_pct : 20;
        const slP = pd.slouched_pct !== undefined ? pd.slouched_pct : 5;

        safeSetText("legend-upright-val", `${upP}%`);
        safeSetText("legend-bent-val", `${bentP}%`);
        safeSetText("legend-slouched-val", `${slP}%`);

        drawSvgDonut("svg-donut-posture", [
            { pct: upP, color: "var(--accent-cyan)" },
            { pct: bentP, color: "var(--accent-primary)" },
            { pct: slP, color: "var(--indigo-11)" }
        ], "GÓC CỘT SỐNG");
    }

    // 3. Area Chart: Đường Cong Cường Độ Rủi Ro
    const riskCurve = analytics.risk_curve || currentHeatmapData || [];
    drawSvgRiskCurve("svg-risk-curve", riskCurve, duration);

    // 4. Multi-Track Actor Timeline (Băng Chuyền Hành Vi Đa Thực Thể)
    const actorTracks = analytics.actor_timeline_tracks || (currentVideoData ? currentVideoData.actor_timeline_tracks : null);
    drawMultiTrackActorTimeline(actorTracks, duration);

    // 5. Ergonomic Scorecard (nếu có trong DOM)
    const scoreCircle = document.getElementById("ergo-score-circle");
    if (scoreCircle) {
        const score = Math.round(analytics.ergonomic_score !== undefined ? analytics.ergonomic_score : 90);
        safeSetText("ergo-score-num", score);
        const scoreOuter = scoreCircle.parentElement;
        if (scoreOuter) {
            const deg = Math.round((score / 100) * 360);
            const col = score >= 80 ? "var(--accent-emerald)" : (score >= 60 ? "var(--accent-amber)" : "var(--accent-crimson)");
            const colText = score >= 80 ? "var(--accent-emerald-text)" : (score >= 60 ? "var(--accent-amber-text)" : "var(--accent-crimson-text)");
            scoreOuter.style.background = `conic-gradient(${col} 0deg ${deg}deg, var(--border-subtle) ${deg}deg 360deg)`;
            scoreOuter.style.boxShadow = "none";
            const numEl = document.getElementById("ergo-score-num");
            if (numEl) numEl.style.color = colText;
        }

        const sitSec = analytics.continuous_sitting_sec || 0;
        const sitM = Math.floor(sitSec / 60);
        const sitS = Math.floor(sitSec % 60);
        safeSetText("ergo-sitting-time", `${String(sitM).padStart(2, '0')}:${String(sitS).padStart(2, '0')}`);

        const healthBadge = document.getElementById("ergo-health-badge");
        if (healthBadge) {
            if (score >= 82) {
                healthBadge.className = "badge badge-safe";
                healthBadge.style.color = "";
                healthBadge.textContent = "Tối ưu";
            } else if (score >= 65) {
                healthBadge.className = "badge badge-warning";
                healthBadge.style.color = "";
                healthBadge.textContent = "Cần điều chỉnh";
            } else {
                healthBadge.className = "badge badge-danger";
                healthBadge.style.color = "";
                healthBadge.textContent = "Cảnh báo";
            }
        }
        safeSetText("ergo-advice-text", analytics.ergonomic_advice || "Cột sống duy trì góc độ giải phẫu học an toàn.");
    }
}

function drawSvgDonut(svgId, segments, centerText) {
    const svg = document.getElementById(svgId);
    if (!svg) return;

    const r = 70;
    const cx = 100;
    const cy = 100;
    const circumference = 2 * Math.PI * r;

    let accumulatedOffset = 0;
    let pathsHtml = "";

    segments.forEach((seg) => {
        const len = (Math.max(0, seg.pct) / 100) * circumference;
        if (len > 0) {
            pathsHtml += `
                <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${seg.color}"
                    stroke-width="20"
                    stroke-dasharray="${len} ${circumference - len}"
                    stroke-dashoffset="${-accumulatedOffset}"
                    stroke-linecap="${segments.length === 1 ? 'round' : 'butt'}"
                    style="transition: stroke-dasharray 0.6s ease;"
                />
            `;
            accumulatedOffset += len;
        }
    });

    if (accumulatedOffset === 0) {
        pathsHtml = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--border-subtle)" stroke-width="20"/>`;
    }

    // Inner text rotated back
    const textHtml = `
        <g transform="rotate(90 100 100)">
            <text x="100" y="96" text-anchor="middle" font-size="11" font-weight="700" fill="var(--text-primary)" font-family="'Be Vietnam Pro', sans-serif">${escapeHtml(centerText)}</text>
            <text x="100" y="112" text-anchor="middle" font-size="9" fill="var(--text-tertiary)" font-family="'Be Vietnam Pro', sans-serif">100% QUY MÔ</text>
        </g>
    `;

    svg.innerHTML = pathsHtml + textHtml;
}

function drawSvgRiskCurve(svgId, curveData, duration) {
    const svg = document.getElementById(svgId);
    const wrapper = document.getElementById("risk-curve-chart-wrapper");
    if (!svg || !wrapper) return;

    const W = 900;
    const H = 220;
    const padTop = 20;
    const padBottom = 30;
    const padLeft = 85;
    const padRight = 20;

    const plotW = W - padLeft - padRight;
    const plotH = H - padTop - padBottom;
    const maxScore = 10.0;

    duration = Math.max(1.0, duration || 30.0);

    let points = curveData;
    if (!points || points.length === 0) {
        points = [
            { time: 0, score: 0.5 },
            { time: duration, score: 0.5 }
        ];
    }

    const coords = points.map(pt => {
        const t = Math.min(duration, Math.max(0, pt.time));
        const s = Math.min(maxScore, Math.max(0, pt.score));
        const x = padLeft + (t / duration) * plotW;
        const y = padTop + (1.0 - (s / maxScore)) * plotH;
        return { x, y, time: t, score: s };
    });

    const dangerY = padTop + (1.0 - (8.0 / maxScore)) * plotH;
    const warnY = padTop + (1.0 - (4.0 / maxScore)) * plotH;

    let pathD = `M ${coords[0].x},${coords[0].y}`;
    for (let i = 1; i < coords.length; i++) {
        pathD += ` L ${coords[i].x},${coords[i].y}`;
    }
    const areaD = `${pathD} L ${coords[coords.length - 1].x},${padTop + plotH} L ${coords[0].x},${padTop + plotH} Z`;

    let timeMarks = "";
    const stepSec = duration <= 20 ? 5 : (duration <= 60 ? 10 : 20);
    for (let sec = 0; sec <= duration; sec += stepSec) {
        const x = padLeft + (sec / duration) * plotW;
        const mm = Math.floor(sec / 60);
        const ss = Math.floor(sec % 60);
        const tStr = `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
        timeMarks += `
            <line x1="${x}" y1="${padTop + plotH}" x2="${x}" y2="${padTop + plotH + 5}" stroke="var(--border-subtle)" stroke-width="1"/>
            <text x="${x}" y="${padTop + plotH + 18}" text-anchor="middle" font-size="10" font-family="'IBM Plex Mono', monospace" fill="var(--text-tertiary)">${tStr}</text>
        `;
    }

    svg.innerHTML = `
        <defs>
            <linearGradient id="riskAreaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="var(--accent-crimson)" stop-opacity="0.35"/>
                <stop offset="50%" stop-color="var(--accent-amber)" stop-opacity="0.20"/>
                <stop offset="100%" stop-color="var(--accent-emerald)" stop-opacity="0.05"/>
            </linearGradient>
        </defs>

        <!-- Grid Lines -->
        <line x1="${padLeft}" y1="${padTop}" x2="${W - padRight}" y2="${padTop}" stroke="var(--border-subtle)" stroke-width="0.8" stroke-dasharray="3 3"/>
        <line x1="${padLeft}" y1="${dangerY}" x2="${W - padRight}" y2="${dangerY}" stroke="var(--accent-crimson)" stroke-width="1.2" stroke-dasharray="4 4"/>
        <line x1="${padLeft}" y1="${warnY}" x2="${W - padRight}" y2="${warnY}" stroke="var(--accent-amber)" stroke-width="0.8" stroke-dasharray="3 3"/>
        <line x1="${padLeft}" y1="${padTop + plotH}" x2="${W - padRight}" y2="${padTop + plotH}" stroke="var(--border-color)" stroke-width="1.2"/>

        <!-- Y Axis Labels -->
        <text x="${padLeft - 8}" y="${dangerY + 3}" text-anchor="end" font-size="9" font-family="'Be Vietnam Pro', sans-serif" fill="var(--accent-crimson-text)">8 — Nguy hiểm</text>
        <text x="${padLeft - 8}" y="${warnY + 3}" text-anchor="end" font-size="9" font-family="'Be Vietnam Pro', sans-serif" fill="var(--accent-amber-text)">4 — Cảnh báo</text>
        <text x="${padLeft - 8}" y="${padTop + plotH + 3}" text-anchor="end" font-size="9" font-family="'Be Vietnam Pro', sans-serif" fill="var(--text-tertiary)">0 — An toàn</text>

        <!-- Time Axis Marks -->
        ${timeMarks}

        <!-- Filled Area -->
        <path d="${areaD}" fill="url(#riskAreaGrad)"/>

        <!-- Stroke Line -->
        <path d="${pathD}" fill="none" stroke="var(--accent-primary)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>

        <!-- Data Circles -->
        ${coords.map(c => `
            <circle cx="${c.x}" cy="${c.y}" r="${c.score >= 8.0 ? '4.5' : '3'}"
                fill="${c.score >= 8.0 ? 'var(--accent-crimson)' : (c.score >= 4.0 ? 'var(--accent-amber)' : 'var(--accent-primary)')}"
                stroke="var(--bg-surface)" stroke-width="1.5"
            />
        `).join('')}
    `;

    // Interactive Click-to-Seek & Hover Tooltip
    const tooltip = document.getElementById("chart-tooltip");
    
    wrapper.onclick = (e) => {
        const rect = wrapper.getBoundingClientRect();
        const svgX = ((e.clientX - rect.left) / rect.width) * W;
        const plotX = Math.max(0, Math.min(plotW, svgX - padLeft));
        const seekSec = (plotX / plotW) * duration;
        seekBothPlayers(seekSec, false, wrapper, `Đồ thị [${formatTime(seekSec)}]`);
    };

    wrapper.onmousemove = (e) => {
        if (!tooltip) return;
        const rect = wrapper.getBoundingClientRect();
        const svgX = ((e.clientX - rect.left) / rect.width) * W;
        const plotX = Math.max(0, Math.min(plotW, svgX - padLeft));
        const hoverSec = (plotX / plotW) * duration;
        const mm = Math.floor(hoverSec / 60);
        const ss = Math.floor(hoverSec % 60);
        const tStr = `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;

        let nearestScore = 0.0;
        let minDiff = 99999;
        points.forEach(p => {
            const diff = Math.abs(p.time - hoverSec);
            if (diff < minDiff) {
                minDiff = diff;
                nearestScore = p.score;
            }
        });

        const scoreCol = nearestScore >= 8 ? 'var(--accent-crimson-text)' : (nearestScore >= 4 ? 'var(--accent-amber-text)' : 'var(--accent-emerald-text)');
        tooltip.innerHTML = `${ICONS.clock} <span class="mono">${tStr}</span> | Nguy cơ: <strong class="mono" style="color: ${scoreCol}">${nearestScore.toFixed(1)}/10</strong>`;
        tooltip.style.left = `${Math.min(rect.width - 150, Math.max(10, e.clientX - rect.left - 60))}px`;
        tooltip.classList.remove("hidden");
    };

    wrapper.onmouseleave = () => {
        if (tooltip) tooltip.classList.add("hidden");
    };
}

function updateChartPlayhead(currentSec, totalDuration) {
    const playhead = document.getElementById("chart-playhead");
    if (!playhead || !totalDuration) return;
    const W = 900;
    const padLeft = 85;
    const plotW = 900 - 85 - 20; // 795
    const ratio = Math.max(0, Math.min(1, currentSec / totalDuration));
    const pct = ((padLeft + ratio * plotW) / W) * 100;
    playhead.style.left = `${pct}%`;
    playhead.classList.remove("hidden");
}

function getSegmentMilestoneTitle(seg) {
    if (!seg) return "Vận động tự nhiên";
    // 1. Direct explicit milestone field if provided by Gemini
    if (seg.event_milestone && typeof seg.event_milestone === "string" && seg.event_milestone.trim()) {
        return seg.event_milestone.trim();
    }
    // 2. Short detailed action
    if (seg.detailed_action && typeof seg.detailed_action === "string" && seg.detailed_action.trim()) {
        const act = seg.detailed_action.trim();
        if (act.length <= 40) return act;
    }
    // 3. Short macro narrative if suitable
    if (seg.macro_narrative && typeof seg.macro_narrative === "string") {
        const macro = seg.macro_narrative.trim();
        if (macro.length > 0 && macro.length <= 35 && !macro.includes(".")) {
            return macro;
        }
    }
    // 4. Infer logically from combined context keywords and severity
    const entList = Array.isArray(seg.entities) ? seg.entities.filter(Boolean) : [];
    const combinedText = [
        seg.scene_summary || "",
        seg.context_description || "",
        seg.detailed_narrative || "",
        entList.map(e => `${(e && e.action) || ''} ${(e && e.role) || ''}`).join(" ")
    ].join(" ").toLowerCase();

    if (combinedText.includes("can ngăn") || combinedText.includes("hạ nhiệt") || combinedText.includes("vãn hồi") || combinedText.includes("can thiệp")) {
        return "Can ngăn / Vãn hồi";
    }
    if (seg.severity === "danger" || combinedText.includes("xô xát") || combinedText.includes("tấn công") || combinedText.includes("đấm") || combinedText.includes("đá") || combinedText.includes("xung đột thể xác") || combinedText.includes("xung đột")) {
        return "Xô xát thể xác";
    }
    if (seg.severity === "warning" || combinedText.includes("tiếp cận") || combinedText.includes("đối đầu") || combinedText.includes("gây hấn") || combinedText.includes("tranh cãi") || combinedText.includes("thủ thế")) {
        return "Tiếp cận đối đầu";
    }
    if (combinedText.includes("ăn") || combinedText.includes("bàn ăn") || combinedText.includes("gia đình") || combinedText.includes("trò chuyện") || combinedText.includes("cơm")) {
        return "Sinh hoạt gia đình";
    }
    
    // 5. Extract first clause from detailed action, macro narrative, or scene summary
    const candidateStr = seg.detailed_action || seg.macro_narrative || seg.scene_summary || "";
    if (candidateStr && typeof candidateStr === "string" && candidateStr.trim()) {
        let firstClause = candidateStr.trim().split(/[.\n;]/)[0].trim();
        if (firstClause.length > 40) firstClause = firstClause.substring(0, 37) + "...";
        if (firstClause) return firstClause;
    }
    return "Vận động tự nhiên";
}

function updateEventFlowPlayhead(curT) {
    if (!currentSegments || currentSegments.length === 0) return;
    currentSegments.forEach(seg => {
        const isActive = curT >= seg.start_sec && curT < seg.end_sec;
        const eventEl = document.getElementById(`event-pill-${seg.segment_id}`);
        const riskEl = document.getElementById(`risk-pill-${seg.segment_id}`);
        if (eventEl) {
            if (isActive) eventEl.classList.add("active-pill");
            else eventEl.classList.remove("active-pill");
        }
        if (riskEl) {
            if (isActive) riskEl.classList.add("active-pill");
            else riskEl.classList.remove("active-pill");
        }
    });
}

function showEventFlowTooltip(e, segIndex) {
    const tooltip = document.getElementById("event-flow-tooltip");
    if (!tooltip || !currentSegments || !currentSegments[segIndex]) return;
    const seg = currentSegments[segIndex];
    const milestone = getSegmentMilestoneTitle(seg);
    const timeStr = `[${formatTime(seg.start_sec)} ➔ ${formatTime(seg.end_sec)}]`;
    const score = (typeof seg.danger_score === 'number' ? seg.danger_score : 0).toFixed(1);
    const numScore = parseFloat(seg.danger_score || 0);
    const isDanger = numScore >= 8.0 || seg.severity === 'danger';
    const isWarn = (!isDanger && (numScore >= 4.0 || seg.severity === 'warning'));
    const sevLabel = isDanger ? 'Nguy hiểm' : (isWarn ? 'Cần chú ý' : 'An toàn');
    
    let actorsList = (seg.entities || []).map(ent => {
        let rawId = String(ent.id || "");
        let cleanId = rawId.replace(/\(Chủ thể chính\)/g, "").trim();
        cleanId = cleanId.replace(/Đối tượng\s*#?(\d+)\s*\((ID\s*#?\1)\)/i, "$2");
        return `<strong>${escapeHtml(cleanId)}</strong>: ${escapeHtml(ent.action || 'Bình thường')}`;
    }).join('<br>');
    if (!actorsList) actorsList = 'Không có đối tượng vi sai';

    tooltip.innerHTML = `
        <div style="font-weight: 700; font-size: 11.5px; margin-bottom: 4px; color: var(--text-primary);">
            ${escapeHtml(seg.segment_id || '')} &bull; ${escapeHtml(timeStr)}
        </div>
        <div style="font-size: 12px; color: var(--accent-blue-text); font-weight: 700; margin-bottom: 6px;">
            Mốc sự kiện: ${escapeHtml(milestone)}
        </div>
        <div style="font-size: 11px; margin-bottom: 6px; color: var(--text-secondary); line-height: 1.4;">
            ${escapeHtml(seg.scene_summary || seg.context_description || 'Phân đoạn ghi nhận tương tác.')}
        </div>
        <div style="font-size: 11px; margin-bottom: 6px; color: var(--text-muted);">
            Cấp độ rủi ro: <strong style="color: ${isDanger ? 'var(--accent-crimson-text)' : (isWarn ? 'var(--accent-amber-text)' : 'var(--accent-emerald-text)')};">${sevLabel} (${score}/10)</strong>
        </div>
        <div style="font-size: 10.5px; color: var(--text-tertiary); border-top: 1px solid var(--border-subtle); padding-top: 5px;">
            ${actorsList}
        </div>
    `;

    tooltip.classList.remove("hidden");
    const rect = e.currentTarget.getBoundingClientRect();
    const container = document.getElementById("actor-tracks-box");
    const containerRect = container ? container.getBoundingClientRect() : { left: 0, top: 0 };
    
    const left = rect.left - containerRect.left + (rect.width / 2) - 130;
    const top = rect.top - containerRect.top - 120;
    tooltip.style.left = `${Math.max(10, left)}px`;
    tooltip.style.top = `${Math.max(10, top)}px`;
}

function hideEventFlowTooltip() {
    const tooltip = document.getElementById("event-flow-tooltip");
    if (tooltip) tooltip.classList.add("hidden");
}

function drawEventCentricFlowStreams(segments, duration) {
    const container = document.getElementById("multi-track-actor-timeline");
    if (!container) return;
    duration = Math.max(1.0, duration || (currentResultDuration || 30.0));

    let segs = segments;
    if (!segs || segs.length === 0) {
        segs = currentSegments || [];
    }

    if (segs.length === 0) {
        container.innerHTML = `
            <div class="empty-state-box empty-state-compact">
                <span class="empty-icon"><svg class="ui-icon empty-svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></span>
                <p class="empty-title">Chưa có dữ liệu dòng diễn biến sự kiện</p>
                <span class="empty-sub">Dòng diễn biến tương tác và phổ màu cảnh báo an ninh toàn cảnh sẽ hiển thị trực quan sau khi hoàn tất phân tích video.</span>
            </div>
        `;
        return;
    }

    // Arrow icon SVG helper
    const arrowSvg = `<div class="stream-flow-arrow"><svg class="ui-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg></div>`;

    // 1. Mạch Diễn Biến Tương Tác (Interaction & Event Narrative Stream)
    let narrativePillsHtml = "";
    segs.forEach((seg, idx) => {
        if (idx > 0) narrativePillsHtml += arrowSvg;
        const milestone = getSegmentMilestoneTitle(seg);
        const startSec = Math.max(0, seg.start_sec);
        const endSec = Math.min(duration, seg.end_sec);
        const segCode = seg.segment_id || `SEG-${String(idx + 1).padStart(2, '0')}`;
        const timeRangeStr = `[${formatTime(startSec)} ➔ ${formatTime(endSec)}]`;
        const titleTooltip = `Mốc ${timeRangeStr}: ${milestone}. Nhấp chuột để tua video đến phân đoạn này.`;

        narrativePillsHtml += `
            <div class="event-stream-pill event-narrative-pill"
                 id="event-pill-${escapeHtml(seg.segment_id)}"
                 title="${escapeHtml(titleTooltip)}"
                 onmouseenter="showEventFlowTooltip(event, ${idx})"
                 onmouseleave="hideEventFlowTooltip()"
                 onclick="seekBothPlayers(${startSec}, false, this, 'Mốc [${formatTime(startSec)} - ${formatTime(endSec)}]')">
                <div class="pill-top-row">
                    <span class="pill-time mono">${timeRangeStr}</span>
                    <span class="pill-seg-code mono">${escapeHtml(segCode)}</span>
                </div>
                <div class="pill-title-text">${escapeHtml(milestone)}</div>
            </div>
        `;
    });

    // 2. Mạch Cảnh Báo An Ninh (Threat & Risk Level Stream)
    let threatPillsHtml = "";
    segs.forEach((seg, idx) => {
        if (idx > 0) threatPillsHtml += arrowSvg;
        const startSec = Math.max(0, seg.start_sec);
        const endSec = Math.min(duration, seg.end_sec);
        const timeRangeStr = `[${formatTime(startSec)} ➔ ${formatTime(endSec)}]`;
        const score = (typeof seg.danger_score === 'number' ? seg.danger_score : 0).toFixed(1);
        const numScore = parseFloat(seg.danger_score || 0);
        const isDanger = numScore >= 8.0 || seg.severity === "danger";
        const isWarn = (!isDanger && (numScore >= 4.0 || seg.severity === "warning"));
        
        let riskClass = isDanger ? "risk-danger" : (isWarn ? "risk-warn" : "risk-safe");
        let riskBadgeText = isDanger ? "NGUY HIỂM" : (isWarn ? "CẦN CHÚ Ý" : "AN TOÀN");

        const tb = seg.telemetry_breakdown || {};
        const maxVelVal = tb.max_velocity !== undefined ? tb.max_velocity : (tb.strike_velocity || 0);
        const maxVelStr = typeof maxVelVal === "number" ? `${maxVelVal} px/s` : String(maxVelVal);
        const minDistVal = tb.min_distance !== undefined ? tb.min_distance : (tb.proximity_dist || null);
        const minDistStr = typeof minDistVal === "number" ? `${minDistVal} px` : (minDistVal ? String(minDistVal) : "> 1.5m");

        const riskTooltip = `${timeRangeStr} ${riskBadgeText} (${score}/10). Vận tốc: ${maxVelStr}, Cự ly: ${minDistStr}. Nhấp để tua video.`;

        threatPillsHtml += `
            <div class="event-stream-pill threat-risk-pill ${riskClass}"
                 id="risk-pill-${escapeHtml(seg.segment_id)}"
                 title="${escapeHtml(riskTooltip)}"
                 onmouseenter="showEventFlowTooltip(event, ${idx})"
                 onmouseleave="hideEventFlowTooltip()"
                 onclick="seekBothPlayers(${startSec}, false, this, 'Mốc [${formatTime(startSec)} - ${formatTime(endSec)}]')">
                <div class="pill-top-row">
                    <span class="pill-time mono">${timeRangeStr}</span>
                    <span class="pill-risk-badge font-mono">${riskBadgeText} (${score}/10)</span>
                </div>
                <div class="pill-metrics-row mono">
                    <span>Vận tốc: ${escapeHtml(maxVelStr)}</span>
                    <span class="pill-metric-sep">|</span>
                    <span>Cự ly: ${escapeHtml(minDistStr)}</span>
                </div>
            </div>
        `;
    });

    // Time Axis Ticks along bottom
    let axisTicksHtml = "";
    const stepSec = duration <= 20 ? 5 : (duration <= 60 ? 10 : 20);
    for (let sec = 0; sec <= duration; sec += stepSec) {
        axisTicksHtml += `<span style="margin-right: 18px;">${formatTime(sec)}</span>`;
    }

    const html = `
        <!-- Mạch 1: Diễn Biến Tương Tác -->
        <div class="stream-track-group">
            <div class="stream-track-header">
                <span class="stream-label">
                    <svg class="ui-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                    Mạch Diễn Biến Tương Tác
                </span>
                <span class="stream-sublabel">Trình tự mốc sự kiện chủ đạo qua thời gian thực</span>
            </div>
            <div class="stream-flow-track" id="narrative-flow-track">
                ${narrativePillsHtml}
            </div>
        </div>

        <!-- Mạch 2: Cảnh Báo An Ninh -->
        <div class="stream-track-group">
            <div class="stream-track-header">
                <span class="stream-label">
                    <svg class="ui-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                    Mạch Cảnh Báo An Ninh
                </span>
                <span class="stream-sublabel">Phổ màu phân cấp rủi ro & chỉ số động học</span>
            </div>
            <div class="stream-flow-track" id="threat-flow-track">
                ${threatPillsHtml}
            </div>
        </div>

        <!-- Trục Thời Gian & Thông Số Tổng Quan -->
        <div class="event-flow-axis-row mono">
            <div class="event-flow-axis-info">
                <span>Trục thời gian: ${axisTicksHtml}</span>
            </div>
            <div class="event-flow-summary">
                <span>Tổng thời lượng: <strong>${formatTime(duration)}</strong> (${segs.length} phân đoạn sự kiện)</span>
            </div>
        </div>
    `;

    container.innerHTML = html;
}

function drawMultiTrackActorTimeline(tracksData, duration) {
    // Forward directly to Event-Centric Flow Streams
    drawEventCentricFlowStreams(currentSegments, duration);
}

function toggleTelemetryDrawer() {
    const drawer = document.getElementById("telemetry-quota-drawer");
    if (!drawer) return;
    drawer.classList.toggle("hidden");
}

function updateQuotaDrawerUI(quotaMatrix, telemetryData) {
    if (!quotaMatrix) return;

    // Update floating bubble badge
    const bubbleBadge = document.getElementById("bubble-tier-badge");
    const tierInfo = telemetryData.model_orchestrator || {};
    const activeTier = tierInfo.active_tier || "tier_1";
    if (bubbleBadge) {
        if (activeTier === "tier_1") {
            bubbleBadge.textContent = "Tier-1";
            bubbleBadge.className = "bubble-badge mono badge-tier1";
        } else if (activeTier === "tier_2") {
            bubbleBadge.textContent = "Tier-2";
            bubbleBadge.className = "bubble-badge mono badge-tier2";
        } else {
            bubbleBadge.textContent = "Tier-3";
            bubbleBadge.className = "bubble-badge mono badge-tier3";
        }
    }

    // Update hardware metrics in drawer
    safeSetText("drawer-fps", `${telemetryData.fps || 0} FPS`);
    const dQueueSize = telemetryData.queue_size !== undefined ? telemetryData.queue_size : (telemetryData.bounded_queue_size || 0);
    const dQueueMax = telemetryData.queue_max !== undefined ? telemetryData.queue_max : (telemetryData.bounded_queue_capacity || 16);
    safeSetText("drawer-queue", `${dQueueSize} / ${dQueueMax} frames`);
    safeSetText("drawer-cpu", `${telemetryData.cpu_percent || 0}%`);
    safeSetText("drawer-ram", `${telemetryData.ram_percent || 0}%`);
    safeSetText("drawer-vram", `${telemetryData.gpu_vram_mb || 0} / ${telemetryData.gpu_vram_total_mb || 8192} MB ${telemetryData.gpu_name || 'GPU'}`);

    // Update realtime Quota Gauges (RPM, RPD & Tokens)
    const rq = telemetryData.realtime_quota;
    if (rq) {
        safeSetText("drawer-rpm-val", `${rq.rpm_used || 0} / ${rq.rpm_limit || 15}`);
        safeSetText("drawer-rpm-rem", `${rq.rpm_remaining !== undefined ? rq.rpm_remaining : 15} req`);
        const rpmBar = document.getElementById("drawer-rpm-bar");
        if (rpmBar) {
            rpmBar.style.width = `${Math.min(100, rq.rpm_percent || 0)}%`;
            if (rq.rpm_percent >= 80) {
                rpmBar.style.background = "var(--accent-crimson)";
            } else if (rq.rpm_percent >= 50) {
                rpmBar.style.background = "var(--accent-amber)";
            } else {
                rpmBar.style.background = "var(--accent-emerald)";
            }
        }

        safeSetText("drawer-rpd-val", `${(rq.rpd_used || 0).toLocaleString()} / ${(rq.rpd_limit || 1500).toLocaleString()}`);
        safeSetText("drawer-rpd-rem", `${(rq.rpd_remaining !== undefined ? rq.rpd_remaining : 1500).toLocaleString()} req`);
        const rpdBar = document.getElementById("drawer-rpd-bar");
        if (rpdBar) {
            rpdBar.style.width = `${Math.min(100, rq.rpd_percent || 0)}%`;
        }

        safeSetText("drawer-tokens-val", `${(rq.tokens_today || 0).toLocaleString()} tokens`);

        if (bubbleBadge && rq.rpm_used > 0) {
            bubbleBadge.textContent = `${activeTier.toUpperCase()} | ${rq.rpm_used}/15 RPM`;
        }
    }

    // Render Quota Matrix cards
    const listEl = document.getElementById("drawer-quota-list");
    if (!listEl) return;

    let itemsHtml = "";
    Object.keys(quotaMatrix).forEach(key => {
        const item = quotaMatrix[key];
        const isActive = item.is_active;
        const activeClass = isActive ? "quota-card-active" : "";
        itemsHtml += `
            <div class="quota-matrix-card ${activeClass}">
                <div class="qmc-header">
                    <div class="qmc-title-group">
                        <strong class="qmc-name">${escapeHtml(item.name)}</strong>
                        <span class="qmc-model mono">${escapeHtml(item.model)}</span>
                    </div>
                    <span class="badge ${isActive ? 'badge-safe' : 'badge-neutral'} mono">${escapeHtml(item.badge)}</span>
                </div>
                <div class="qmc-details">
                    <div class="qmc-detail-row">
                        <span class="qmc-label">Trạng thái:</span>
                        <strong class="qmc-val" style="color: ${isActive ? 'var(--accent-emerald-text)' : 'var(--text-secondary)'}">${escapeHtml(item.status)}</strong>
                    </div>
                    <div class="qmc-detail-row">
                        <span class="qmc-label">Hạn mức:</span>
                        <span class="qmc-val mono">${escapeHtml(item.limit)}</span>
                    </div>
                </div>
            </div>
        `;
    });
    listEl.innerHTML = itemsHtml;
}

// ==============================================================================
// OS KERNEL SYNCHRONIZATION LAB & 3-STAGE PIPELINE REPORT
// ==============================================================================
function updateThreadStateBadge(elemId, stateStr) {
    const el = document.getElementById(elemId);
    if (!el) return;
    const st = String(stateStr || "READY").toUpperCase();
    el.textContent = st;
    if (st.includes("RUNNING")) {
        el.className = "badge badge-safe mono";
    } else if (st.includes("CRITICAL") || st.includes("THROTTLED")) {
        el.className = "badge badge-warning mono";
    } else if (st.includes("WAITING")) {
        el.className = "badge badge-outline mono";
    } else {
        el.className = "badge badge-neutral mono";
    }
}

function toggleInlineTelemetryPanel() {
    const panel = document.getElementById("telemetry-floating-panel");
    const statusBadge = document.getElementById("btn-telemetry-status");
    const toggleBtn = document.getElementById("btn-toggle-telemetry");
    if (!panel) return;
    const isNowHidden = panel.classList.toggle("hidden");
    if (statusBadge) {
        statusBadge.textContent = isNowHidden ? "ẨN" : "HIỂN THỊ";
        statusBadge.className = isNowHidden ? "badge badge-neutral mono" : "badge badge-safe mono";
    }
    if (toggleBtn) {
        toggleBtn.classList.toggle("active-toggle", !isNowHidden);
    }
}

function closeTelemetryPanel() {
    const panel = document.getElementById("telemetry-floating-panel");
    const backdrop = document.getElementById("telemetry-backdrop");
    if (backdrop) backdrop.classList.add("hidden");
    if (panel) panel.classList.add("hidden");
    const statusBadge = document.getElementById("btn-telemetry-status");
    if (statusBadge) {
        statusBadge.textContent = "ẨN";
        statusBadge.className = "badge badge-neutral mono";
    }
}

// Trạng thái đồng bộ của Luồng Tùy Chỉnh Tài Nguyên (Dùng chung cho cả Live Camera và Import Video)
let osBranchZState = {
    cap: 16,
    delay: 0,
    policy: "drop_oldest",
    zFps: 30.0,
    zDropPct: 0.0,
    zLatencyMs: 33,
    zLagSlots: 0,
    zSkipStride: 1,
    isStall: false
};

function syncAllOSLabControls(capVal, delayVal, policyVal) {
    const c1 = document.getElementById("os-lab-cap-slider");
    const d1 = document.getElementById("os-lab-delay-slider");
    const p1 = document.getElementById("os-lab-policy-select");
    if (c1 && parseInt(c1.value, 10) !== capVal) c1.value = capVal;
    if (d1 && parseInt(d1.value, 10) !== delayVal) d1.value = delayVal;
    if (p1 && p1.value !== policyVal) p1.value = policyVal;

    const c2 = document.getElementById("vid-z-cap-slider");
    const d2 = document.getElementById("vid-z-delay-slider");
    const p2 = document.getElementById("vid-z-policy-select");
    if (c2 && parseInt(c2.value, 10) !== capVal) c2.value = capVal;
    if (d2 && parseInt(d2.value, 10) !== delayVal) d2.value = delayVal;
    if (p2 && p2.value !== policyVal) p2.value = policyVal;

    const pfBuf = document.getElementById("pf-z-buf");
    const pfDelay = document.getElementById("pf-z-delay");
    const pfPolicy = document.getElementById("pf-z-policy");
    if (pfBuf && String(pfBuf.value) !== String(capVal)) {
        const opts = Array.from(pfBuf.options).map(o => parseInt(o.value, 10));
        if (opts.includes(capVal)) pfBuf.value = String(capVal);
    }
    if (pfDelay && String(pfDelay.value) !== String(delayVal)) {
        const opts = Array.from(pfDelay.options).map(o => parseInt(o.value, 10));
        if (opts.includes(delayVal)) pfDelay.value = String(delayVal);
    }
    if (pfPolicy && pfPolicy.value !== policyVal) {
        pfPolicy.value = policyVal;
    }

    const ramMb = ((capVal * 1280 * 720 * 3) / (1024 * 1024)).toFixed(2);
    safeSetText("os-lab-cap-display", `N = ${capVal} (${ramMb} MB)`);
    safeSetText("os-lab-delay-display", `${delayVal} ms`);
    safeSetText("os-lab-policy-display", policyVal === "drop_oldest" ? "Drop-Oldest + Priority" : "Block-Producer + FIFO");

    safeSetText("vid-z-cap-val", `N = ${capVal} (${ramMb} MB)`);
    safeSetText("vid-z-delay-val", `${delayVal} ms`);
}

function applySplitResourcePreset(capVal, delayVal, policyVal) {
    if (stallRecoveryTimer) {
        clearInterval(stallRecoveryTimer);
        stallRecoveryTimer = null;
    }
    const banner = document.getElementById("os-stall-alert-banner");
    if (banner) banner.classList.add("hidden");

    syncAllOSLabControls(capVal, delayVal, policyVal);
    updateDualModeEvaluation(capVal, delayVal, policyVal);
    commitOSLabConfig(false);
}

function selectPreflightZPreset(presetKey, capVal, delayVal, policyVal) {
    document.querySelectorAll(".preflight-z-btn").forEach(btn => btn.classList.remove("active"));
    const activeBtn = document.getElementById(`pf-btn-${presetKey}`);
    if (activeBtn) activeBtn.classList.add("active");

    applySplitResourcePreset(capVal, delayVal, policyVal);
}

function syncPreflightZInputs(showNotification = false) {
    const pfBuf = document.getElementById("pf-z-buf");
    const pfDelay = document.getElementById("pf-z-delay");
    const pfPolicy = document.getElementById("pf-z-policy");
    if (!pfBuf || !pfDelay || !pfPolicy) return;

    const capVal = parseInt(pfBuf.value, 10) || 4;
    const delayVal = parseInt(pfDelay.value, 10) || 25;
    const policyVal = pfPolicy.value || "block_fifo";

    syncAllOSLabControls(capVal, delayVal, policyVal);
    updateDualModeEvaluation(capVal, delayVal, policyVal);
    commitOSLabConfig(showNotification);
}

function onOSLabSliderInput() {
    const capSlider = document.getElementById("os-lab-cap-slider");
    const delaySlider = document.getElementById("os-lab-delay-slider");
    const policySelect = document.getElementById("os-lab-policy-select");
    const capVal = capSlider ? parseInt(capSlider.value, 10) : 16;
    const delayVal = delaySlider ? parseInt(delaySlider.value, 10) : 0;
    const policyVal = policySelect ? policySelect.value : "drop_oldest";

    syncAllOSLabControls(capVal, delayVal, policyVal);
    updateDualModeEvaluation(capVal, delayVal, policyVal);
}

function onOSLabPolicyChange() {
    onOSLabSliderInput();
    commitOSLabConfig(false);
}

function onVideoZControlInput() {
    const capSlider = document.getElementById("vid-z-cap-slider");
    const delaySlider = document.getElementById("vid-z-delay-slider");
    const policySelect = document.getElementById("vid-z-policy-select");
    const capVal = capSlider ? parseInt(capSlider.value, 10) : 16;
    const delayVal = delaySlider ? parseInt(delaySlider.value, 10) : 0;
    const policyVal = policySelect ? policySelect.value : "drop_oldest";

    syncAllOSLabControls(capVal, delayVal, policyVal);
    updateDualModeEvaluation(capVal, delayVal, policyVal);
    commitOSLabConfig(false);
}

function applyVideoZUnderProvisionPreset() {
    applySplitResourcePreset(4, 75, "block_fifo");
    showToast("Đã áp dụng kịch bản thiếu hụt tài nguyên (N=4, Trễ=75ms, FIFO).", "warning");
}

function updateDualModeEvaluation(capVal = 16, delayVal = 0, policyVal = null) {
    const pol = policyVal || (document.getElementById("os-lab-policy-select") ? document.getElementById("os-lab-policy-select").value : "drop_oldest");
    const ramY = 42.19;
    const ramZ = Number(((capVal * 1280 * 720 * 3) / (1024 * 1024)).toFixed(2));
    const ramRatio = Number((capVal / 16.0).toFixed(2));

    // Tính toán hạn mức ngân sách phần cứng (dành >= 20% dự trữ cho Hệ điều hành máy chủ)
    const branchYPct = 20.0;
    const branchZPct = Math.min(60.0, Number((6.0 + (capVal / 64.0) * 34.0 + (delayVal / 200.0) * 20.0).toFixed(1)));
    const reservePct = Number((100.0 - branchYPct - branchZPct).toFixed(1));

    // Tính toán thông số thực tế của Luồng Tùy Chỉnh Tài Nguyên
    let zFps = 30.0;
    let zDropPct = 0.0;
    let zLatencyMs = 33;
    let zLagSlots = 0;
    let zSkipStride = 1;

    if (delayVal === 0) {
        zFps = capVal >= 8 ? 30.0 : Number((24.0 + (capVal / 8.0) * 6.0).toFixed(1));
        zDropPct = capVal >= 8 ? 0.0 : Number(((8 - capVal) * 3.5).toFixed(1));
        zLatencyMs = capVal <= 16 ? Math.round(capVal * 33.3 * 0.25) : Math.round(33 + (capVal - 16) * 14.5);
        zLagSlots = capVal <= 16 ? 0 : Math.min(36, Math.round((capVal - 16) * 0.65));
        zSkipStride = capVal >= 8 ? 1 : 2;
    } else {
        zFps = Number((1000.0 / (33.3 + delayVal)).toFixed(1));
        zDropPct = Number(((delayVal / (33.3 + delayVal)) * 100.0).toFixed(1));
        if (capVal < 16) {
            zDropPct = Math.min(95.0, Number((zDropPct + (16 - capVal) * 1.4).toFixed(1)));
        }
        zLatencyMs = Math.round(capVal * 33.3 + delayVal * 1.5);
        zLagSlots = Math.min(44, Math.max(2, Math.round((capVal / 64.0) * 28 + (delayVal / 200.0) * 18)));
        zSkipStride = Math.max(2, Math.min(10, Math.round(30.0 / Math.max(2.5, zFps))));
    }

    const isStall = delayVal > 80;
    osBranchZState = {
        cap: capVal,
        delay: delayVal,
        policy: pol,
        zFps,
        zDropPct,
        zLatencyMs,
        zLagSlots,
        zSkipStride,
        isStall
    };

    // Cập nhật thanh phân bổ ngân sách phần cứng
    const segY = document.getElementById("budget-seg-y");
    const segZ = document.getElementById("budget-seg-z");
    const segRes = document.getElementById("budget-seg-reserve");
    if (segY) segY.style.width = `${branchYPct}%`;
    if (segZ) {
        segZ.style.width = `${branchZPct}%`;
        segZ.classList.toggle("seg-z-warn", (capVal !== 16 || delayVal > 0 || pol !== "drop_oldest") && !isStall);
        segZ.classList.toggle("seg-z-danger", isStall);
    }
    if (segRes) segRes.style.width = `${reservePct}%`;

    safeSetText("budget-label-y", `Luồng Chuẩn: ${branchYPct.toFixed(1)}% (${ramY} MB)`);
    safeSetText("budget-label-z", `Luồng Tùy Chỉnh: ${branchZPct.toFixed(1)}% (${ramZ} MB)`);
    safeSetText("budget-label-reserve", `Dự Trữ Hệ Điều Hành: ${reservePct.toFixed(1)}% (Khóa cứng ≥ 20%)`);

    const sweetBadge = document.getElementById("os-sweet-spot-badge");
    let sweetTitle = "Điểm Cân Bằng Tối Ưu (Chuẩn Khuyến Nghị)";
    let sweetClass = "badge-safe";
    let sweetVerdict = "Luồng Tùy Chỉnh đang khớp 100% với Luồng Chuẩn Khuyến Nghị (N=16, 0ms, Drop-Oldest + Priority): Đạt trần 30.0 FPS, độ trễ 33ms và bảo toàn 100% sự kiện với mức RAM tối ưu 42.19 MB.";

    if (capVal === 16 && delayVal === 0 && pol === "drop_oldest") {
        // Optimal
    } else if (capVal > 16 && delayVal === 0 && pol === "drop_oldest") {
        sweetTitle = `Cấp Phát Dư Thừa (Tốn gấp ${ramRatio}x RAM)`;
        sweetClass = "badge-warning";
        sweetVerdict = `Dù cấp phát bộ đệm lớn gấp ${ramRatio}x lần mức khuyến nghị (${ramZ} MB so với 42.19 MB), tốc độ đầu ra không thể vượt trần 30.0 FPS nhưng lại gây lãng phí RAM và tạo độ trễ hàng đợi (Bufferbloat ~${zLatencyMs} ms).`;
    } else {
        sweetTitle = isStall ? "Quá Tải Hàng Đợi · Ngắt Mạch Bảo Vệ" : "Cấu Hình Lệch Chuẩn · Suy Giảm Chất Lượng AI";
        sweetClass = isStall ? "badge-danger" : "badge-warning";
        sweetVerdict = `Do bộ đệm (N=${capVal}), độ trễ xử lý (${delayVal}ms) hoặc chính sách (${pol === "drop_oldest" ? "Drop-Oldest" : "Block-FIFO"}) chưa tối ưu, tốc độ sụt giảm còn ~${zFps} FPS (rơi ${zDropPct}% khung hình), khiến kết quả nhận diện AI bên phải bị trễ và sai lệch so với bên trái.`;
    }

    if (sweetBadge) {
        sweetBadge.textContent = sweetTitle;
        sweetBadge.className = `badge ${sweetClass} mono`;
    }
    safeSetText("os-sweet-spot-verdict", sweetVerdict);

    // Show/hide stall alert banner
    const stallBanner = document.getElementById("os-stall-alert-banner");
    if (stallBanner) {
        stallBanner.classList.toggle("hidden", delayVal <= 80);
    }

    // Đồng bộ tức thì dữ liệu bảng AI và báo cáo ngay khi kéo thanh trượt trong chế độ So Sánh Song Song
    if (typeof isLiveParallelActive !== "undefined" && isLiveParallelActive && typeof updateLiveParallelReportsAndLogs === "function") {
        updateLiveParallelReportsAndLogs();
    }
    if (typeof isVideoParallelActive !== "undefined" && isVideoParallelActive && typeof populateVideoParallelSplitView === "function") {
        populateVideoParallelSplitView();
    }
    if (typeof renderHeatmapZTrack === "function") {
        renderHeatmapZTrack(currentHeatmapData, currentResultDuration);
    }
}

let stallRecoveryTimer = null;
function simulateControlledStall() {
    syncAllOSLabControls(64, 200, "block_fifo");
    updateDualModeEvaluation(64, 200, "block_fifo");
    commitOSLabConfig(true);

    const banner = document.getElementById("os-stall-alert-banner");
    if (banner) banner.classList.remove("hidden");

    let countdownSec = 5.0;
    const cdEl = document.getElementById("os-stall-countdown");
    if (cdEl) cdEl.textContent = `Tự phục hồi an toàn sau: ${countdownSec.toFixed(1)}s`;

    if (stallRecoveryTimer) clearInterval(stallRecoveryTimer);
    stallRecoveryTimer = setInterval(() => {
        countdownSec -= 0.5;
        if (cdEl) cdEl.textContent = `Tự phục hồi an toàn sau: ${Math.max(0, countdownSec).toFixed(1)}s`;
        if (countdownSec <= 0) {
            clearInterval(stallRecoveryTimer);
            stallRecoveryTimer = null;
            resetToHardwareOptimal();
            showToast("Hệ thống đã tự động hoàn nguyên về cấu hình khuyến nghị tối ưu RTX 5060.", "success");
        }
    }, 500);

    showToast("Đang giả lập nguy cơ sập luồng (Khóa cứng ở cận trên RAM 50MB để bảo vệ máy).", "warning");
}

function resetToHardwareOptimal() {
    if (stallRecoveryTimer) {
        clearInterval(stallRecoveryTimer);
        stallRecoveryTimer = null;
    }
    syncAllOSLabControls(16, 0, "drop_oldest");
    const banner = document.getElementById("os-stall-alert-banner");
    if (banner) banner.classList.add("hidden");

    updateDualModeEvaluation(16, 0, "drop_oldest");
    commitOSLabConfig(false);
    showToast("Đã khôi phục thông số khuyến nghị chuẩn máy: N=16, Độ trễ=0ms, Priority (RTX 5060).", "info");
}

async function runOSLiveBenchmark() {
    const btn = document.getElementById("btn-run-os-bench");
    const capSlider = document.getElementById("os-lab-cap-slider");
    const delaySlider = document.getElementById("os-lab-delay-slider");
    const capVal = capSlider ? parseInt(capSlider.value, 10) : 16;
    const delayVal = delaySlider ? parseInt(delaySlider.value, 10) : 0;

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner" style="display:inline-block; width:12px; height:12px; border:2px solid currentColor; border-top-color:transparent; border-radius:50%; animation:spin 0.6s linear infinite; margin-right:6px;"></span> Đang đo đạc thực tế 50 khung...`;
    }

    try {
        const resp = await fetch("/api/os_lab/benchmark", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ capacity: capVal, consumer_delay_ms: delayVal, frames_count: 50 })
        });
        if (resp.ok) {
            const data = await resp.json();
            const resBox = document.getElementById("os-bench-results");
            if (resBox) resBox.classList.remove("hidden");

            safeSetText("ob-res-prod-fps", `${data.measured_producer_fps} FPS`);
            safeSetText("ob-res-cons-fps", `${data.measured_consumer_fps} FPS`);
            safeSetText("ob-res-drop-count", `${data.actual_dropped_frames} khung (${data.drop_rate_pct}%)`);
            safeSetText("ob-res-latency", `${data.measured_latency_ms} ms`);
            safeSetText("ob-res-ram", `${data.ram_usage_mb} MB / ${data.ram_ceiling_mb} MB`);
            safeSetText("ob-res-verdict", data.verdict);
            showToast("Thực nghiệm đo đạc 50 khung hình hoàn tất thành công.", "success");
        }
    } catch (e) {
        console.error("Lỗi chạy benchmark OS:", e);
        showToast("Lỗi khi chạy thực nghiệm đo đạc.", "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg class="ui-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> <span>Chạy Thực Nghiệm Kiểm Chứng (50 Khung Hình)</span>`;
        }
    }
}

async function commitOSLabConfig(triggerBurst = false) {
    const capSlider = document.getElementById("os-lab-cap-slider");
    const delaySlider = document.getElementById("os-lab-delay-slider");
    const capVal = capSlider ? parseInt(capSlider.value, 10) : 16;
    const delayVal = delaySlider ? parseInt(delaySlider.value, 10) : 0;

    try {
        await fetch("/api/os_lab/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                buffer_capacity: capVal,
                consumer_delay_ms: delayVal,
                reset_counters: false,
                trigger_burst: triggerBurst
            })
        });
        await fetchTelemetry();
    } catch (e) {
        console.error("Lỗi cập nhật cấu hình OS Lab:", e);
    }
}

async function applyOSLabPreset(capVal, delayVal, triggerBurst = true) {
    const capSlider = document.getElementById("os-lab-cap-slider");
    const delaySlider = document.getElementById("os-lab-delay-slider");
    if (capSlider) capSlider.value = capVal;
    if (delaySlider) delaySlider.value = delayVal;
    onOSLabSliderInput();
    await commitOSLabConfig(triggerBurst);
    showToast(`Đã áp dụng kịch bản HĐH: Bounded Buffer N=${capVal}, Độ trễ Consumer=${delayVal}ms`, "info");
}

async function triggerOSLabStressBurst() {
    await commitOSLabConfig(true);
    showToast("Đang phát xung 75 khung hình qua ThreadSafeBoundedBuffer để kiểm chứng đồng bộ hóa...", "info");
}

async function resetOSLabCounters() {
    try {
        await fetch("/api/os_lab/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reset_counters: true })
        });
        await fetchTelemetry();
        showToast("Đã đặt lại bộ đếm Mutex Lock, Condition Variable và Drop-Oldest về 0.", "info");
    } catch (e) {
        console.error("Lỗi reset OS Lab:", e);
    }
}

function renderOSPipelineReport(osRep, result) {
    if (!osRep) return;
    const st1 = osRep.stage1_reader || {};
    const st2 = osRep.stage2_inference || {};
    const st3 = osRep.stage3_writer || {};
    const b1 = osRep.raw_buffer || {};
    const b2 = osRep.writer_buffer || {};

    safeSetText("os-st1-time", `${Number(st1.active_time_sec || 0).toFixed(2)}s`);
    safeSetText("os-st1-fps", `${Number(st1.throughput_fps || 0).toFixed(1)} FPS`);
    safeSetText("os-st2-time", `${Number(st2.active_time_sec || 0).toFixed(2)}s`);
    safeSetText("os-st2-fps", `${Number(st2.throughput_fps || 0).toFixed(1)} FPS`);
    safeSetText("os-st3-time", `${Number(st3.active_time_sec || 0).toFixed(2)}s`);
    safeSetText("os-st3-fps", `${Number(st3.throughput_fps || 0).toFixed(1)} FPS`);

    safeSetText("os-buf1-hwm", `${b1.high_water_mark || 0} / ${b1.capacity || 16}`);
    safeSetText("os-buf1-mutex", `${(b1.mutex_lock_count || 0).toLocaleString()}`);
    safeSetText("os-buf1-wait", `${((b1.not_empty_wait_count || 0) + (b1.not_full_wait_count || 0)).toLocaleString()}`);

    safeSetText("os-buf2-hwm", `${b2.high_water_mark || 0} / ${b2.capacity || 16}`);
    safeSetText("os-buf2-mutex", `${(b2.mutex_lock_count || 0).toLocaleString()}`);
    safeSetText("os-buf2-wait", `${((b2.not_empty_wait_count || 0) + (b2.not_full_wait_count || 0)).toLocaleString()}`);

    const seqTime = Number(osRep.sequential_time_sec || result.processing_time_seconds || 1.0).toFixed(2);
    const parTime = Number(osRep.parallel_wall_time_sec || result.processing_time_seconds || 1.0).toFixed(2);
    const speedup = Number(osRep.speedup_factor || 1.25).toFixed(2);
    const overlap = Number(osRep.concurrency_overlap_pct || 20.0).toFixed(1);

    safeSetText("os-rep-speedup-badge", `Tăng tốc đa luồng: ${speedup}x`);
    safeSetText("os-rep-seq-time", `${seqTime}s`);
    safeSetText("os-rep-par-time", `${parTime}s`);
    safeSetText("os-rep-overlap", `${speedup}x · Chồng lấp ${overlap}%`);
    safeSetText("os-rep-sync-total", `${(osRep.total_mutex_locks || 0).toLocaleString()} locks · ${(osRep.total_condition_signals || 0).toLocaleString()} signals`);
    safeSetText("os-rep-ram-bound", `${Number(osRep.ram_ceiling_mb || osRep.bounded_ram_ceiling_mb || 84.38).toFixed(2)} MB · _SENTINEL`);

    // Cache final frame deck for reopening Live OS Pipeline Modal after job completion
    const finalFps = Number(st2.throughput_fps || (result && result.overall_fps) || 30.0);
    latestPipelineLiveState = {
        is_completed: true,
        progress_pct: 100,
        current_frame: (result && result.total_frames) || st2.frames_handled || 0,
        total_frames: (result && result.total_frames) || st1.frames_handled || 0,
        current_fps: finalFps,
        ms_per_frame: finalFps > 0 ? Number((1000 / finalFps).toFixed(1)) : 28.0,
        raw_q: b1.high_water_mark || 0,
        writer_q: b2.high_water_mark || 0,
        q_max: b1.capacity || 16,
        mutex_locks: osRep.total_mutex_locks || 0,
        cond_waits: osRep.total_condition_waits || 0,
        cond_signals: osRep.total_condition_signals || 0,
        frame_deck: osRep.final_frame_deck || (latestPipelineLiveState ? latestPipelineLiveState.frame_deck : []),
        trace_logs: osRep.final_trace_logs || (latestPipelineLiveState ? latestPipelineLiveState.trace_logs : [])
    };
}

// ==============================================================================
// LIVE OS PIPELINE & OVERLAPPING FRAME-STREAM INSPECTOR MODAL
// ==============================================================================
let latestPipelineLiveState = null;
let pinnedConveyorFrameIdx = null;
let flipbookTimer = null;
let flipbookCursorIdx = 0;
let flipbookLastFrameIdx = -1;
let flipbookEndHoldTicks = 0;
let flipbookSpeedMode = "normal"; // "slow" | "normal"
let flipbookOnionSkin = true;
let lastRenderedDeckSignature = "";

function formatImgDataUrl(b64) {
    if (!b64 || typeof b64 !== "string") return "";
    return b64.startsWith("data:image") ? b64 : `data:image/jpeg;base64,${b64}`;
}

function formatActiveIdsText(activeIds, persons) {
    if (Array.isArray(activeIds) && activeIds.length > 0) {
        return activeIds.join(", ");
    }
    if (typeof activeIds === "string" && activeIds.trim().length > 0 && activeIds !== "Không có") {
        return activeIds.trim();
    }
    return `${persons || 0} đối tượng`;
}

function startFlipbookLoop() {
    stopFlipbookLoop();
    const intervalMs = flipbookSpeedMode === "slow" ? 360 : 190;
    flipbookTimer = setInterval(stepFlipbookTick, intervalMs);
}

function stopFlipbookLoop() {
    if (flipbookTimer) {
        clearInterval(flipbookTimer);
        flipbookTimer = null;
    }
}

function setFlipbookSpeed(mode) {
    flipbookSpeedMode = mode === "slow" ? "slow" : "normal";
    const slowBtn = document.getElementById("btn-flip-slow");
    const normBtn = document.getElementById("btn-flip-normal");
    if (slowBtn) slowBtn.classList.toggle("active", flipbookSpeedMode === "slow");
    if (normBtn) normBtn.classList.toggle("active", flipbookSpeedMode === "normal");
    startFlipbookLoop();
    stepFlipbookTick();
}

function toggleFlipbookOnionSkin() {
    flipbookOnionSkin = !flipbookOnionSkin;
    const onionBtn = document.getElementById("btn-flip-onion");
    if (onionBtn) onionBtn.classList.toggle("active", flipbookOnionSkin);
    stepFlipbookTick();
}

function stepFlipbookTick() {
    const modal = document.getElementById("os-live-pipeline-modal");
    if (!modal || modal.classList.contains("hidden")) return;
    if (!latestPipelineLiveState || !Array.isArray(latestPipelineLiveState.frame_deck)) return;
    const deck = latestPipelineLiveState.frame_deck;
    if (deck.length === 0) return;

    let idx = 0;
    if (pinnedConveyorFrameIdx !== null && deck[pinnedConveyorFrameIdx]) {
        idx = pinnedConveyorFrameIdx;
        flipbookLastFrameIdx = Number(deck[idx].frame_idx || 0);
    } else if (!latestPipelineLiveState.is_completed) {
        // Khi đang nạp và xử lý trực tiếp: chỉ tiến về phía trước theo frame_idx mới nhất,
        // không quay vòng ngược về khung đầu để tránh cảm giác lặp lại khi chờ khung mới.
        const nextForwardIdx = deck.findIndex(f => Number(f.frame_idx || 0) > flipbookLastFrameIdx);
        if (nextForwardIdx !== -1) {
            idx = nextForwardIdx;
        } else {
            idx = deck.length - 1;
        }
        flipbookCursorIdx = idx;
        flipbookLastFrameIdx = Number(deck[idx].frame_idx || 0);
    } else {
        // Khi đã hoàn tất 100%: phát tuần tự mượt mà qua 10 khung hình cuối và giữ nhịp nghỉ ngắn ở khung cuối trước khi lặp
        if (flipbookCursorIdx >= deck.length - 1) {
            if (flipbookEndHoldTicks < 2) {
                flipbookEndHoldTicks += 1;
                idx = deck.length - 1;
            } else {
                flipbookEndHoldTicks = 0;
                flipbookCursorIdx = 0;
                idx = 0;
            }
        } else {
            flipbookCursorIdx = (flipbookCursorIdx + 1) % deck.length;
            idx = flipbookCursorIdx;
        }
        flipbookLastFrameIdx = Number(deck[idx].frame_idx || 0);
    }

    const cur = deck[idx];
    if (!cur) return;

    const flipImg = document.getElementById("os-modal-flipbook-img");
    const ghostImg = document.getElementById("os-modal-flipbook-ghost-img");
    const emptyFlip = document.getElementById("os-modal-flipbook-empty");
    const curSrc = formatImgDataUrl(cur.pose_b64 || cur.raw_b64);

    if (flipImg && curSrc) {
        if (flipImg.getAttribute("data-frame-idx") !== String(cur.frame_idx)) {
            flipImg.src = curSrc;
            flipImg.setAttribute("data-frame-idx", String(cur.frame_idx));
        }
        flipImg.classList.remove("hidden");
        if (emptyFlip) emptyFlip.classList.add("hidden");
    }

    if (ghostImg) {
        if (flipbookOnionSkin && idx > 0 && deck.length > 1) {
            const prevFrame = deck[idx - 1];
            const prevSrc = formatImgDataUrl(prevFrame && (prevFrame.pose_b64 || prevFrame.raw_b64));
            if (prevSrc) {
                if (ghostImg.getAttribute("data-frame-idx") !== String(prevFrame.frame_idx)) {
                    ghostImg.src = prevSrc;
                    ghostImg.setAttribute("data-frame-idx", String(prevFrame.frame_idx));
                }
                ghostImg.classList.remove("hidden");
            } else {
                ghostImg.classList.add("hidden");
            }
        } else {
            ghostImg.classList.add("hidden");
        }
    }

    const modeSuffix = latestPipelineLiveState.is_completed ? " · Phát lại chuỗi 10 khung" : " · Dòng thời gian thực";
    safeSetText(
        "os-flipbook-step-label",
        `Tờ ${idx + 1}/${deck.length} · Khung #${cur.frame_idx || 0} · ${cur.time_str || "00:00"}${modeSuffix}`
    );

    const dotsEl = document.getElementById("os-flipbook-dots");
    if (dotsEl) {
        if (dotsEl.children.length !== deck.length) {
            dotsEl.innerHTML = deck
                .map((_, dIdx) => `<span class="flip-step-dot${dIdx === idx ? " active" : ""}"></span>`)
                .join("");
        } else {
            Array.from(dotsEl.children).forEach((dotEl, dIdx) => {
                dotEl.classList.toggle("active", dIdx === idx);
            });
        }
    }

    // Synchronize active highlight on the bottom overlapping filmstrip cards without rebuilding DOM
    const cascadeEl = document.getElementById("os-conveyor-cascade-fan");
    if (cascadeEl) {
        const cards = cascadeEl.querySelectorAll(".os-frame-card");
        cards.forEach((cardEl, cIdx) => {
            cardEl.classList.toggle("flip-active-card", cIdx === idx);
        });
    }
}

function openLivePipelineModal() {
    const modal = document.getElementById("os-live-pipeline-modal");
    if (!modal) return;
    pinnedConveyorFrameIdx = null;
    flipbookEndHoldTicks = 0;
    modal.classList.remove("hidden");
    if (latestPipelineLiveState) {
        renderLivePipelineModalDOM(latestPipelineLiveState);
    }
    startFlipbookLoop();
    stepFlipbookTick();
}

function closeLivePipelineModal(e) {
    if (e && e.target && e.target !== e.currentTarget && !e.target.classList.contains("modal-close-btn") && !e.target.classList.contains("btn-primary")) {
        return;
    }
    const modal = document.getElementById("os-live-pipeline-modal");
    if (modal) modal.classList.add("hidden");
    pinnedConveyorFrameIdx = null;
    stopFlipbookLoop();
}

function updateLivePipelineModal(stateObj) {
    if (!stateObj) return;
    // Preserve previous frame_deck if current poll packet has empty deck during final stage transition
    if ((!stateObj.frame_deck || stateObj.frame_deck.length === 0) && latestPipelineLiveState && latestPipelineLiveState.frame_deck && latestPipelineLiveState.frame_deck.length > 0) {
        stateObj.frame_deck = latestPipelineLiveState.frame_deck;
    }
    if ((!stateObj.trace_logs || stateObj.trace_logs.length === 0) && latestPipelineLiveState && latestPipelineLiveState.trace_logs && latestPipelineLiveState.trace_logs.length > 0) {
        stateObj.trace_logs = latestPipelineLiveState.trace_logs;
    }
    // Reset forward tracker if a new video job starts from a lower frame index
    if (Array.isArray(stateObj.frame_deck) && stateObj.frame_deck.length > 0) {
        const newestIdx = Number(stateObj.frame_deck[stateObj.frame_deck.length - 1].frame_idx || 0);
        if (newestIdx < flipbookLastFrameIdx) {
            flipbookLastFrameIdx = -1;
            flipbookCursorIdx = 0;
            lastRenderedDeckSignature = "";
        }
    }
    latestPipelineLiveState = stateObj;

    const modal = document.getElementById("os-live-pipeline-modal");
    if (modal && !modal.classList.contains("hidden")) {
        renderLivePipelineModalDOM(stateObj);
    }
}

function renderLivePipelineModalDOM(st) {
    const statusBadge = document.getElementById("os-modal-status-badge");
    const pulseDot = document.getElementById("os-modal-pulse-dot");
    if (statusBadge) {
        if (st.is_completed) {
            statusBadge.textContent = "ĐÃ HOÀN TẤT 100%";
            statusBadge.className = "badge badge-safe mono";
            if (pulseDot) pulseDot.style.opacity = "0.4";
        } else {
            statusBadge.textContent = `ĐANG XỬ LÝ TRỰC TIẾP · ${st.progress_pct || 0}%`;
            statusBadge.className = "badge badge-safe mono";
            if (pulseDot) pulseDot.style.opacity = "1";
        }
    }

    safeSetText("os-modal-fps", `${st.current_fps || 0} FPS`);
    safeSetText("os-modal-ms", `${st.ms_per_frame || '--'} ms/khung`);
    safeSetText("os-modal-mutex", `${Number(st.mutex_locks || 0).toLocaleString()} lượt`);
    safeSetText("os-modal-cond", `${Number(st.cond_signals || 0).toLocaleString()} / ${Number(st.cond_waits || 0).toLocaleString()}`);

    const qMax = Math.max(1, st.q_max || 16);
    const rawQ = st.raw_q || 0;
    const wrQ = st.writer_q || 0;
    safeSetText("os-modal-rawbuf-text", `${rawQ} / ${qMax}`);
    safeSetText("os-modal-writerbuf-text", `${wrQ} / ${qMax}`);

    const rawBar = document.getElementById("os-modal-rawbuf-bar");
    const wrBar = document.getElementById("os-modal-writerbuf-bar");
    if (rawBar) rawBar.style.width = `${Math.min(100, Math.round((rawQ / qMax) * 100))}%`;
    if (wrBar) wrBar.style.width = `${Math.min(100, Math.round((wrQ / qMax) * 100))}%`;

    const deck = st.frame_deck || [];
    if (deck.length === 0) return;

    const activeEntry = (pinnedConveyorFrameIdx !== null && deck[pinnedConveyorFrameIdx])
        ? deck[pinnedConveyorFrameIdx]
        : deck[deck.length - 1];

    updateLeftSingleFrameInspector(activeEntry, st);

    // Incremental DOM update for Bottom Full-Width Cinema Filmstrip (prevents flickering & image teardown)
    const cascadeEl = document.getElementById("os-conveyor-cascade-fan");
    if (cascadeEl) {
        const deckSig = deck.map(f => f.frame_idx).join(",");
        if (deckSig !== lastRenderedDeckSignature || cascadeEl.children.length !== deck.length) {
            lastRenderedDeckSignature = deckSig;
            const existingMap = new Map();
            Array.from(cascadeEl.querySelectorAll(".os-frame-card")).forEach(el => {
                const fKey = el.getAttribute("data-frame-idx");
                if (fKey) existingMap.set(fKey, el);
            });

            const activeHighlightIdx = pinnedConveyorFrameIdx !== null
                ? pinnedConveyorFrameIdx
                : Math.min(deck.length - 1, Math.max(0, flipbookCursorIdx));

            const fragment = document.createDocumentFragment();
            deck.forEach((f, idx) => {
                const fKey = String(f.frame_idx);
                let cardEl = existingMap.get(fKey);
                if (!cardEl) {
                    cardEl = document.createElement("div");
                    cardEl.className = "os-frame-card os-frame-card-enter";
                    cardEl.setAttribute("data-frame-idx", fKey);
                    const src = formatImgDataUrl(f.pose_b64 || f.raw_b64);
                    cardEl.innerHTML = `
                        <img src="${src}" alt="Annotated frame ${f.frame_idx}" decoding="async" />
                        <span class="os-frame-card-tag mono">Khung #${f.frame_idx}</span>
                        <span class="os-frame-card-step mono">Tờ ${idx + 1}/${deck.length}</span>
                        <div class="os-frame-card-foot mono">
                            <span>${escapeHtml(f.time_str || '00:00')}</span>
                            <span>17 khớp · ${f.persons || 0} ID</span>
                        </div>
                    `;
                } else {
                    cardEl.classList.remove("os-frame-card-enter");
                    const stepSpan = cardEl.querySelector(".os-frame-card-step");
                    if (stepSpan) stepSpan.textContent = `Tờ ${idx + 1}/${deck.length}`;
                }
                cardEl.setAttribute("data-deck-idx", String(idx));
                cardEl.style.zIndex = String(15 + idx);
                cardEl.classList.toggle("flip-active-card", idx === activeHighlightIdx);
                cardEl.onmouseenter = () => previewConveyorFrame(idx);
                cardEl.onmouseleave = () => releaseConveyorFrame();
                cardEl.onclick = () => previewConveyorFrame(idx);
                fragment.appendChild(cardEl);
            });
            cascadeEl.replaceChildren(fragment);
        }
    }

    if (!flipbookTimer) {
        startFlipbookLoop();
        stepFlipbookTick();
    }
}

function updateLeftSingleFrameInspector(f, st) {
    if (!f) return;
    const liveImg = document.getElementById("os-modal-live-img");
    const emptyBox = document.getElementById("os-modal-viewport-empty");
    const rawPip = document.getElementById("os-modal-raw-pip");
    const rawCompareImg = document.getElementById("os-modal-raw-compare-img");

    const poseSrc = formatImgDataUrl(f.pose_b64 || f.raw_b64);
    const rawSrc = formatImgDataUrl(f.raw_b64 || f.pose_b64);

    if (liveImg && poseSrc) {
        if (liveImg.getAttribute("data-frame-idx") !== String(f.frame_idx)) {
            liveImg.src = poseSrc;
            liveImg.setAttribute("data-frame-idx", String(f.frame_idx));
        }
        liveImg.classList.remove("hidden");
        if (emptyBox) emptyBox.classList.add("hidden");
    }
    if (rawPip && rawCompareImg && rawSrc) {
        if (rawCompareImg.getAttribute("data-frame-idx") !== String(f.frame_idx)) {
            rawCompareImg.src = rawSrc;
            rawCompareImg.setAttribute("data-frame-idx", String(f.frame_idx));
        }
        rawPip.classList.remove("hidden");
    }

    const totalF = (st && st.total_frames) || f.total_frames || 0;
    safeSetText("os-modal-frame-counter", `Khung #${f.frame_idx || 0} / ${totalF}`);
    safeSetText("os-modal-time-readout", f.time_str || "00:00");
    const idsList = formatActiveIdsText(f.active_ids, f.persons);
    safeSetText("os-modal-hud-ids", `Chủ thể: ${idsList}`);
    safeSetText("os-modal-hud-latency", `Chu kỳ suy luận: ${f.latency_ms || (st && st.ms_per_frame) || '--'} ms/khung`);
}

function previewConveyorFrame(deckIdx) {
    if (!latestPipelineLiveState || !latestPipelineLiveState.frame_deck) return;
    const f = latestPipelineLiveState.frame_deck[deckIdx];
    if (!f) return;
    pinnedConveyorFrameIdx = deckIdx;
    updateLeftSingleFrameInspector(f, latestPipelineLiveState);
    stepFlipbookTick();
}

function releaseConveyorFrame() {
    pinnedConveyorFrameIdx = null;
}

// ==============================================================================
// OS EXPERIMENTAL TELEMETRY SERVICES
// ==============================================================================
let activeLabScenario = "buffer"; // "buffer" | "deadlock" | "memory"
let currentLabBufferPolicy = "drop_oldest";
let labWatchdogInterval = null;
let labWatchdogSeconds = 3.0;

function openOSExperimentModal() {
    const modal = document.getElementById("os-experiment-modal");
    if (!modal) return;
    modal.classList.remove("hidden");
    switchLabScenario(activeLabScenario || "buffer");
}

function closeOSExperimentModal(e) {
    if (e && e.target && e.target !== e.currentTarget && !e.target.classList.contains("modal-close-btn") && !e.target.classList.contains("btn-primary")) {
        return;
    }
    const modal = document.getElementById("os-experiment-modal");
    if (modal) modal.classList.add("hidden");
    if (labWatchdogInterval) {
        clearInterval(labWatchdogInterval);
        labWatchdogInterval = null;
    }
}

function switchLabScenario(scenarioId) {
    activeLabScenario = scenarioId;
    const tabBufferBtn = document.getElementById("tab-lab-buffer-btn");
    const tabDeadlockBtn = document.getElementById("tab-lab-deadlock-btn");
    const tabMemoryBtn = document.getElementById("tab-lab-memory-btn");
    const panelBuffer = document.getElementById("lab-scenario-buffer");
    const panelDeadlock = document.getElementById("lab-scenario-deadlock");
    const panelMemory = document.getElementById("lab-scenario-memory");

    if (tabBufferBtn) tabBufferBtn.classList.toggle("active", scenarioId === "buffer");
    if (tabDeadlockBtn) tabDeadlockBtn.classList.toggle("active", scenarioId === "deadlock");
    if (tabMemoryBtn) tabMemoryBtn.classList.toggle("active", scenarioId === "memory");

    if (panelBuffer) panelBuffer.classList.toggle("active", scenarioId === "buffer");
    if (panelDeadlock) panelDeadlock.classList.toggle("active", scenarioId === "deadlock");
    if (panelMemory) panelMemory.classList.toggle("active", scenarioId === "memory");

    if (scenarioId === "buffer") {
        fetchLabBufferTelemetry();
    } else if (scenarioId === "deadlock") {
        pollLabDeadlockStatus();
    } else if (scenarioId === "memory") {
        runLabMemorySim("fifo");
    }
}

// SCENARIO 1: BUFFERBLOAT & BOUNDED BUFFER
async function fetchLabBufferTelemetry() {
    try {
        const resp = await fetch("/api/os_lab/scenarios/buffer");
        if (!resp.ok) return;
        const data = await resp.json();
        updateLabBufferDOM(data);
    } catch (e) {
        console.error("fetchLabBufferTelemetry error:", e);
    }
}

function updateLabBufferDOM(data) {
    if (!data) return;
    safeSetText("lab-buf-cap-val", `N = ${data.capacity}`);
    safeSetText("lab-buf-delay-val", `${data.consumer_delay_ms} ms`);
    safeSetText("lab-buf-policy-badge", data.policy === "block_producer" ? "Block-Producer" : "Drop-Oldest");

    const capSlider = document.getElementById("lab-buf-cap-slider");
    if (capSlider && document.activeElement !== capSlider) capSlider.value = data.capacity;
    const delaySlider = document.getElementById("lab-buf-delay-slider");
    if (delaySlider && document.activeElement !== delaySlider) delaySlider.value = data.consumer_delay_ms;

    const btnDrop = document.getElementById("btn-pol-drop");
    const btnBlock = document.getElementById("btn-pol-block");
    if (btnDrop) btnDrop.classList.toggle("active-toggle", data.policy === "drop_oldest");
    if (btnBlock) btnBlock.classList.toggle("active-toggle", data.policy === "block_producer");

    safeSetText("lab-res-queue", `${data.queue_fill} / ${data.capacity} (${data.queue_fill_pct}%)`);
    safeSetText("lab-res-latency", `${data.latency_ms} ms`);
    safeSetText("lab-res-drop", `${data.drop_rate_pct}%`);
    safeSetText("lab-res-ram", `${data.ram_usage_mb} MB / ${data.ram_ceiling_mb} MB`);

    const fidelityEl = document.getElementById("lab-res-fidelity");
    if (fidelityEl) {
        fidelityEl.textContent = data.status_badge || "HOÀN HẢO";
        fidelityEl.className = `badge ${data.badge_class || "badge-safe"} mono`;
    }
    safeSetText("lab-res-score", `${data.threat_score} / 10`);
    safeSetText("lab-res-diagnosis", data.ai_diagnosis || "--");
}

let labBufferDebounceTimer = null;
function onLabBufferKnobChange() {
    const capSlider = document.getElementById("lab-buf-cap-slider");
    const delaySlider = document.getElementById("lab-buf-delay-slider");
    const capVal = capSlider ? parseInt(capSlider.value, 10) : 16;
    const delayVal = delaySlider ? parseInt(delaySlider.value, 10) : 0;

    safeSetText("lab-buf-cap-val", `N = ${capVal}`);
    safeSetText("lab-buf-delay-val", `${delayVal} ms`);

    clearTimeout(labBufferDebounceTimer);
    labBufferDebounceTimer = setTimeout(async () => {
        try {
            const resp = await fetch("/api/os_lab/scenarios/buffer", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    capacity: capVal,
                    consumer_delay_ms: delayVal,
                    policy: currentLabBufferPolicy
                })
            });
            if (resp.ok) {
                const data = await resp.json();
                updateLabBufferDOM(data);
            }
        } catch (e) {
            console.error("onLabBufferKnobChange error:", e);
        }
    }, 120);
}

async function setLabBufferPolicy(policy) {
    currentLabBufferPolicy = policy;
    const capSlider = document.getElementById("lab-buf-cap-slider");
    const delaySlider = document.getElementById("lab-buf-delay-slider");
    const capVal = capSlider ? parseInt(capSlider.value, 10) : 16;
    const delayVal = delaySlider ? parseInt(delaySlider.value, 10) : 0;

    try {
        const resp = await fetch("/api/os_lab/scenarios/buffer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                capacity: capVal,
                consumer_delay_ms: delayVal,
                policy: currentLabBufferPolicy
            })
        });
        if (resp.ok) {
            const data = await resp.json();
            updateLabBufferDOM(data);
        }
    } catch (e) {
        console.error("setLabBufferPolicy error:", e);
    }
}

async function applyLabBufferPreset(cap, delay, policy) {
    currentLabBufferPolicy = policy;
    const btnBalanced = document.getElementById("btn-lab-pre-balanced");
    const btnBloat = document.getElementById("btn-lab-pre-bloat");
    const btnDrop = document.getElementById("btn-lab-pre-drop");

    if (btnBalanced) btnBalanced.classList.toggle("active-preset", cap === 16 && delay === 0);
    if (btnBloat) btnBloat.classList.toggle("active-preset", cap === 48 && delay === 85);
    if (btnDrop) btnDrop.classList.toggle("active-preset", cap === 2 && delay === 45);

    try {
        const resp = await fetch("/api/os_lab/scenarios/buffer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                capacity: cap,
                consumer_delay_ms: delay,
                policy: policy
            })
        });
        if (resp.ok) {
            const data = await resp.json();
            updateLabBufferDOM(data);
        }
    } catch (e) {
        console.error("applyLabBufferPreset error:", e);
    }
}

// SCENARIO 2: DEADLOCK & RESOURCE ALLOCATION GRAPH (RAG)
async function triggerLabDeadlock() {
    const triggerBtn = document.getElementById("btn-trigger-deadlock");
    const resolveBtn = document.getElementById("btn-resolve-deadlock");
    if (triggerBtn) triggerBtn.disabled = true;
    if (resolveBtn) resolveBtn.disabled = false;

    try {
        const resp = await fetch("/api/os_lab/scenarios/deadlock/trigger", { method: "POST" });
        if (resp.ok) {
            const data = await resp.json();
            updateLabDeadlockDOM(data);
            startLabWatchdogCountdown(3.0);
        }
    } catch (e) {
        console.error("triggerLabDeadlock error:", e);
        if (triggerBtn) triggerBtn.disabled = false;
    }
}

async function resolveLabDeadlock(method = "banker_preemption") {
    const resolveBtn = document.getElementById("btn-resolve-deadlock");
    if (resolveBtn) resolveBtn.disabled = true;

    try {
        const resp = await fetch("/api/os_lab/scenarios/deadlock/resolve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ method: method })
        });
        if (resp.ok) {
            const data = await resp.json();
            stopLabWatchdogCountdown();
            updateLabDeadlockDOM(data);
            const triggerBtn = document.getElementById("btn-trigger-deadlock");
            if (triggerBtn) triggerBtn.disabled = false;
        }
    } catch (e) {
        console.error("resolveLabDeadlock error:", e);
    }
}

async function pollLabDeadlockStatus() {
    try {
        const resp = await fetch("/api/os_lab/scenarios/deadlock");
        if (resp.ok) {
            const data = await resp.json();
            updateLabDeadlockDOM(data);
        }
    } catch (e) {
        console.error("pollLabDeadlockStatus error:", e);
    }
}

function startLabWatchdogCountdown(initialSec = 3.0) {
    stopLabWatchdogCountdown();
    let remaining = initialSec;
    const timerEl = document.getElementById("lab-watchdog-timer");
    const barEl = document.getElementById("lab-watchdog-bar");

    labWatchdogInterval = setInterval(async () => {
        remaining -= 0.1;
        if (remaining <= 0) {
            remaining = 0;
            stopLabWatchdogCountdown();
            await pollLabDeadlockStatus();
            const triggerBtn = document.getElementById("btn-trigger-deadlock");
            const resolveBtn = document.getElementById("btn-resolve-deadlock");
            if (triggerBtn) triggerBtn.disabled = false;
            if (resolveBtn) resolveBtn.disabled = true;
        }
        if (timerEl) timerEl.textContent = `${remaining.toFixed(1)}s`;
        if (barEl) {
            const pct = Math.round(((3.0 - remaining) / 3.0) * 100);
            barEl.style.width = `${pct}%`;
        }
    }, 100);
}

function stopLabWatchdogCountdown() {
    if (labWatchdogInterval) {
        clearInterval(labWatchdogInterval);
        labWatchdogInterval = null;
    }
    const timerEl = document.getElementById("lab-watchdog-timer");
    const barEl = document.getElementById("lab-watchdog-bar");
    if (timerEl) timerEl.textContent = "3.0s";
    if (barEl) barEl.style.width = "0%";
}

function updateLabDeadlockDOM(data) {
    if (!data) return;
    safeSetText("lab-dl-video-state", data.video_state || "--");
    safeSetText("lab-dl-cycle", data.cycle_detected ? "Chu trình phát hiện: T1 ➔ R2 ➔ T2 ➔ R1 ➔ T1 (Deadlock!)" : "Không có chu trình (An toàn)");
    safeSetText("lab-dl-ai-impact", data.resolution_reason || data.ai_impact || "--");

    const statusBadge = document.getElementById("lab-rag-status-badge");
    if (statusBadge) {
        if (data.deadlock_state === "DEADLOCK_ACTIVE") {
            statusBadge.textContent = "CHU TRÌNH CHỜ VÒNG TRÒN (DEADLOCK)";
            statusBadge.className = "badge badge-danger mono";
        } else if (data.deadlock_state === "RESOLVED") {
            statusBadge.textContent = "ĐÃ GỠ BẾ TẮC (RESOLVED)";
            statusBadge.className = "badge badge-safe mono";
        } else {
            statusBadge.textContent = "KHÔNG BẾ TẮC (NORMAL)";
            statusBadge.className = "badge badge-safe mono";
        }
    }

    renderRAGGraph(data.rag_nodes || [], data.rag_edges || [], data.cycle_detected || false);
}

function renderRAGGraph(nodes, edges, cycleDetected) {
    const svg = document.getElementById("os-rag-svg");
    if (!svg) return;

    const isDark = document.documentElement.getAttribute("data-theme") !== "light";
    const bgNodeThread = isDark ? "#1e293b" : "#e2e8f0";
    const bgNodeResource = isDark ? "#0f172a" : "#f1f5f9";
    const strokeNormal = isDark ? "#475569" : "#cbd5e1";
    const textPrimary = isDark ? "#f8fafc" : "#0f172a";
    const textMuted = isDark ? "#94a3b8" : "#64748b";

    let html = `
        <defs>
            <marker id="arrow-normal" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#3b82f6" />
            </marker>
            <marker id="arrow-cycle" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#ef4444" />
            </marker>
            <marker id="arrow-resolved" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#10b981" />
            </marker>
        </defs>
    `;

    // Coordinates:
    // T1 (Thread AI): circle cx=130, cy=60, r=32
    // R2 (Resource GPU): rect x=460, y=28, w=110, h=64
    // T2 (Thread Writer): circle cx=515, cy=160, r=32
    // R1 (Resource FrameBuffer): rect x=75, y=128, w=110, h=64

    // Edges
    if (cycleDetected) {
        // T1 -> R2 (Request edge)
        html += `<path d="M 162 60 L 452 60" stroke="#ef4444" stroke-width="2.5" class="rag-edge-cycle" fill="none" marker-end="url(#arrow-cycle)" />`;
        html += `<text x="307" y="52" fill="#ef4444" font-size="10.5" font-family="'Be Vietnam Pro', sans-serif" font-weight="700" text-anchor="middle">T1 YÊU CẦU R2</text>`;

        // R2 -> T2 (Assignment edge)
        html += `<path d="M 515 92 L 515 120" stroke="#ef4444" stroke-width="2.5" class="rag-edge-cycle" fill="none" marker-end="url(#arrow-cycle)" />`;
        html += `<text x="525" y="112" fill="#ef4444" font-size="10.5" font-family="'Be Vietnam Pro', sans-serif" font-weight="700">R2 ĐANG GIỮ BỞI T2</text>`;

        // T2 -> R1 (Request edge)
        html += `<path d="M 483 160 L 193 160" stroke="#ef4444" stroke-width="2.5" class="rag-edge-cycle" fill="none" marker-end="url(#arrow-cycle)" />`;
        html += `<text x="338" y="174" fill="#ef4444" font-size="10.5" font-family="'Be Vietnam Pro', sans-serif" font-weight="700" text-anchor="middle">T2 YÊU CẦU R1</text>`;

        // R1 -> T1 (Assignment edge)
        html += `<path d="M 130 128 L 130 100" stroke="#ef4444" stroke-width="2.5" class="rag-edge-cycle" fill="none" marker-end="url(#arrow-cycle)" />`;
        html += `<text x="140" y="118" fill="#ef4444" font-size="10.5" font-family="'Be Vietnam Pro', sans-serif" font-weight="700">R1 ĐANG GIỮ BỞI T1</text>`;
    } else {
        // Normal safe flow
        html += `<path d="M 162 60 L 452 60" stroke="#3b82f6" stroke-width="1.8" stroke-dasharray="4 3" fill="none" marker-end="url(#arrow-normal)" />`;
        html += `<text x="307" y="52" fill="#3b82f6" font-size="10" font-family="'Be Vietnam Pro', sans-serif" text-anchor="middle">Hàng đợi điều phối an toàn</text>`;

        html += `<path d="M 483 160 L 193 160" stroke="#10b981" stroke-width="2" fill="none" marker-end="url(#arrow-resolved)" />`;
        html += `<text x="338" y="175" fill="#10b981" font-size="10" font-family="'Be Vietnam Pro', sans-serif" text-anchor="middle">Tuần tự giải phóng khóa</text>`;
    }

    // Node T1 (Thread Circle)
    html += `
        <circle cx="130" cy="60" r="32" fill="${bgNodeThread}" stroke="${cycleDetected ? '#ef4444' : '#3b82f6'}" stroke-width="2.5" />
        <text x="130" y="56" fill="${textPrimary}" font-size="11" font-weight="700" text-anchor="middle">T1</text>
        <text x="130" y="70" fill="${textMuted}" font-size="9" text-anchor="middle">AI Worker</text>
    `;

    // Node R2 (Resource Rect)
    html += `
        <rect x="460" y="28" width="110" height="64" rx="6" fill="${bgNodeResource}" stroke="${cycleDetected ? '#ef4444' : strokeNormal}" stroke-width="2" />
        <text x="515" y="54" fill="${textPrimary}" font-size="11" font-weight="700" text-anchor="middle">R2 (GPU)</text>
        <text x="515" y="72" fill="${cycleDetected ? '#f87171' : textMuted}" font-size="9.5" text-anchor="middle">${cycleDetected ? 'Khóa bị tranh chấp' : 'Khóa tài nguyên'}</text>
    `;

    // Node T2 (Thread Circle)
    html += `
        <circle cx="515" cy="160" r="32" fill="${bgNodeThread}" stroke="${cycleDetected ? '#ef4444' : '#3b82f6'}" stroke-width="2.5" />
        <text x="515" y="156" fill="${textPrimary}" font-size="11" font-weight="700" text-anchor="middle">T2</text>
        <text x="515" y="170" fill="${textMuted}" font-size="9" text-anchor="middle">Writer Stream</text>
    `;

    // Node R1 (Resource Rect)
    html += `
        <rect x="75" y="128" width="110" height="64" rx="6" fill="${bgNodeResource}" stroke="${cycleDetected ? '#ef4444' : strokeNormal}" stroke-width="2" />
        <text x="130" y="154" fill="${textPrimary}" font-size="11" font-weight="700" text-anchor="middle">R1 (Buffer)</text>
        <text x="130" y="172" fill="${cycleDetected ? '#f87171' : textMuted}" font-size="9.5" text-anchor="middle">${cycleDetected ? 'Khóa bị giữ kín' : 'Khóa hàng đợi đệm'}</text>
    `;

    svg.innerHTML = html;
}

// SCENARIO 3: KEYFRAME MEMORY EVICTION SIMULATOR (FIFO VS THREAT-PRIORITY)
async function runLabMemorySim(policy = "fifo") {
    const btnFifo = document.getElementById("btn-mem-fifo");
    const btnPriority = document.getElementById("btn-mem-priority");
    if (btnFifo) btnFifo.classList.toggle("active-toggle", policy === "fifo");
    if (btnPriority) btnPriority.classList.toggle("active-toggle", policy !== "fifo");

    try {
        const resp = await fetch("/api/os_lab/scenarios/memory_eviction", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ policy: policy })
        });
        if (resp.ok) {
            const data = await resp.json();
            updateLabMemoryDOM(data);
        }
    } catch (e) {
        console.error("runLabMemorySim error:", e);
    }
}

function updateLabMemoryDOM(data) {
    if (!data) return;
    safeSetText("lab-mem-policy-badge", `Chính sách: ${data.policy_name}`);

    // Render 3 RAM Slots
    const slotsGrid = document.getElementById("lab-ram-slots-grid");
    if (slotsGrid && Array.isArray(data.final_slots)) {
        slotsGrid.innerHTML = data.final_slots.map((s, idx) => {
            const isCombat = s.is_combat || s.threat_score >= 8.0;
            const cardClass = isCombat ? "slot-combat" : "slot-calm";
            const badgeClass = isCombat ? "badge-danger" : "badge-safe";
            return `
                <div class="os-ram-slot-card ${cardClass}">
                    <div class="os-ram-slot-top">
                        <span class="slot-index-badge mono">RAM SLOT #${idx + 1}</span>
                        <span class="badge ${badgeClass} mono">${s.threat_score.toFixed(1)} / 10</span>
                    </div>
                    <strong class="slot-frame-title mono">${s.id} · ${s.time}</strong>
                    <span class="slot-action-desc">${escapeHtml(s.action)}</span>
                </div>
            `;
        }).join("");
    }

    // Render Timeline Eviction Table
    const tableBody = document.getElementById("lab-mem-table-body");
    if (tableBody && Array.isArray(data.slots_log)) {
        tableBody.innerHTML = data.slots_log.map(item => {
            const isEvictLoss = item.evicted_frame === "KF-02";
            const heldSpan = item.held_combat_frame
                ? `<span class="badge badge-safe mono" style="font-size: 9.5px;">CÒN TRONG RAM (KF-02)</span>`
                : `<span class="badge badge-danger mono" style="font-size: 9.5px;">MẤT DỮ LIỆU BẠO LỰC</span>`;
            return `
                <tr>
                    <td class="mono">#${item.step}</td>
                    <td class="mono"><strong>${item.incoming_frame}</strong> (${item.incoming_score.toFixed(1)})</td>
                    <td>${item.incoming_score >= 8.0 ? '<span class="badge badge-danger mono" style="font-size: 9.5px;">Xung đột đỉnh</span>' : '<span class="badge badge-safe mono" style="font-size: 9.5px;">Bình thường</span>'}</td>
                    <td class="mono" style="${isEvictLoss ? 'color: var(--accent-crimson); font-weight: 700;' : ''}">${item.evicted_frame}</td>
                    <td class="mono">[${item.ram_slots.join(", ")}]</td>
                    <td>${heldSpan}</td>
                </tr>
            `;
        }).join("");
    }

    // Render Verdict Box
    safeSetText("lab-mem-verdict-title", data.gemini_verdict || "--");
    safeSetText("lab-mem-verdict-desc", data.gemini_explanation || "--");
    safeSetText("lab-mem-verdict-critique", data.policy_critique || "--");

    const verdictBadge = document.getElementById("lab-mem-verdict-badge");
    if (verdictBadge) {
        verdictBadge.textContent = data.verdict_accuracy || "--";
        verdictBadge.className = `badge ${data.accuracy_class || "badge-safe"} mono`;
    }
}

// ==============================================================================
// FULL-PAGE 50/50 PARALLEL SPLIT-SCREEN ENGINE (ZERO EXTRA GEMINI QUOTA)
// ==============================================================================
let isLiveParallelActive = false;
let liveParallelAnimId = null;
let liveRingBuffer = [];
const MAX_RING_BUFFER_SLOTS = 48;
let liveTickCounter = 0;
let cachedSnapshotFallbackImg = null;
let cachedSnapshotFallbackUrl = "";

let isVideoParallelActive = false;
let videoParallelAnimId = null;
let videoRingBuffer = [];
let videoTickCounter = 0;

function getElementMediaDimensions(el, fallbackW = 1280, fallbackH = 720) {
    if (!el) return { w: fallbackW, h: fallbackH };
    const w = el.videoWidth || el.naturalWidth || el.width || fallbackW;
    const h = el.videoHeight || el.naturalHeight || el.height || fallbackH;
    return { w: w > 0 ? w : fallbackW, h: h > 0 ? h : fallbackH };
}

function drawImageContain(ctx, sourceEl, destW = 1280, destH = 720) {
    if (!ctx || !sourceEl) return;
    const { w: srcW, h: srcH } = getElementMediaDimensions(sourceEl, destW, destH);
    ctx.fillStyle = "#090d16";
    ctx.fillRect(0, 0, destW, destH);
    const scale = Math.min(destW / srcW, destH / srcH);
    const drawW = Math.round(srcW * scale);
    const drawH = Math.round(srcH * scale);
    const offsetX = Math.round((destW - drawW) / 2);
    const offsetY = Math.round((destH - drawH) / 2);
    try {
        ctx.drawImage(sourceEl, offsetX, offsetY, drawW, drawH);
    } catch (e) {
        // Ignore unready frame draw
    }
}

function pushFrameToRingBuffer(ring, sourceEl, width = 1280, height = 720) {
    const offCanvas = ring.length >= MAX_RING_BUFFER_SLOTS ? ring.shift() : document.createElement("canvas");
    if (offCanvas.width !== width) offCanvas.width = width;
    if (offCanvas.height !== height) offCanvas.height = height;
    const offCtx = offCanvas.getContext("2d");
    drawImageContain(offCtx, sourceEl, width, height);
    ring.push(offCanvas);
}

function getLatestRealSnapshotElement() {
    if (typeof cachedLogs !== "undefined" && Array.isArray(cachedLogs) && cachedLogs.length > 0) {
        const snapUrl = cachedLogs[0].snapshot_url;
        if (snapUrl) {
            if (!cachedSnapshotFallbackImg || cachedSnapshotFallbackUrl !== snapUrl) {
                cachedSnapshotFallbackUrl = snapUrl;
                cachedSnapshotFallbackImg = new Image();
                cachedSnapshotFallbackImg.src = snapUrl;
            }
            if (cachedSnapshotFallbackImg.complete && cachedSnapshotFallbackImg.naturalWidth > 10) {
                return cachedSnapshotFallbackImg;
            }
        }
    }
    return null;
}

function drawZDiagnosticWatermark(ctx, w, h, st) {
    // Giữ khung hình sạch hoàn toàn, không vẽ hộp chữ đè lên video hay camera.
    if (st && st.isStall) {
        ctx.save();
        ctx.strokeStyle = "rgba(239, 68, 68, 0.75)";
        ctx.lineWidth = 4;
        ctx.strokeRect(2, 2, w - 4, h - 4);
        ctx.restore();
    }
}

function updateLiveParallelReportsAndLogs() {
    const st = osBranchZState;
    const ramMb = ((st.cap * 1280 * 720 * 3) / (1024 * 1024)).toFixed(2);
    const polText = st.policy === "drop_oldest" ? "Priority" : "Block-FIFO";
    const isOptimal = (st.cap === 16 && st.delay === 0 && st.policy === "drop_oldest");
    const isOverProvisioned = (st.cap > 16 && st.delay === 0 && st.policy === "drop_oldest");

    safeSetText("live-split-z-config-text", `N = ${st.cap} (${ramMb} MB) · ${st.delay} ms · ${polText}`);
    safeSetText("live-split-z-fps", `${st.zFps} FPS`);
    safeSetText("live-split-z-lat", `~${st.zLatencyMs} ms`);
    safeSetText("live-split-z-drop", `${st.zDropPct}%`);
    safeSetText("live-split-z-ram", `${ramMb} MB`);

    const zThreatEl = document.getElementById("live-z-rep-threat");
    if (isOptimal) {
        if (zThreatEl) {
            zThreatEl.textContent = "ĐỒNG BỘ 100%";
            zThreatEl.className = "badge badge-safe";
        }
    } else if (isOverProvisioned) {
        const ratio = (st.cap / 16.0).toFixed(1);
        if (zThreatEl) {
            zThreatEl.textContent = `DƯ ${ratio}x RAM · TRỄ +${st.zLatencyMs}ms`;
            zThreatEl.className = "badge badge-warning";
        }
    } else {
        if (zThreatEl) {
            zThreatEl.textContent = st.isStall ? "NGẮT MẠCH · LỆCH MẪU" : `SAI LỆCH · RƠI ${st.zDropPct}%`;
            zThreatEl.className = st.isStall ? "badge badge-danger" : "badge badge-warning";
        }
    }

    const yList = document.getElementById("live-y-log-list");
    const zList = document.getElementById("live-z-log-list");
    const hasRealLogs = (typeof cachedLogs !== "undefined" && Array.isArray(cachedLogs) && cachedLogs.length > 0);
    const sourceLogs = hasRealLogs ? cachedLogs : [];

    // Tính toán thống kê cho Cột Trái (Luồng Chuẩn Khuyến Nghị)
    let ySafe = 0, yWarn = 0, yDanger = 0;
    sourceLogs.forEach(item => {
        if (item.severity === "danger") yDanger += 1;
        else if (item.severity === "warning") yWarn += 1;
        else ySafe += 1;
    });
    const baseErgoText = document.getElementById("session-ergo-score") ? document.getElementById("session-ergo-score").textContent : "100 / 100";
    const baseErgoNum = parseInt(baseErgoText, 10) || 100;

    safeSetText("live-y-safe-count", String(ySafe));
    safeSetText("live-y-warn-count", String(yWarn));
    safeSetText("live-y-danger-count", String(yDanger));
    safeSetText("live-y-rep-ergo", baseErgoText);

    if (sourceLogs.length === 0) {
        const emptyHtml = `
            <tr class="empty-row">
                <td colspan="7" class="empty-cell">
                    <div class="empty-state-box">
                        <p class="empty-title">Chưa có bản ghi nhận diện tư thế</p>
                        <span class="empty-sub">Bật camera hoặc chụp Snapshot để đối chiếu trực tiếp hai luồng.</span>
                    </div>
                </td>
            </tr>
        `;
        if (yList) yList.innerHTML = emptyHtml;
        if (zList) zList.innerHTML = emptyHtml;

        if (isOptimal || isOverProvisioned) {
            safeSetText("live-z-rep-ergo", baseErgoText);
        } else {
            const degradedErgo = Math.max(38, baseErgoNum - Math.round(st.zDropPct * 0.55) - (st.policy === "block_fifo" ? 15 : 5));
            safeSetText("live-z-rep-ergo", `${degradedErgo} / 100`);
        }
        return;
    }

    // Render Bảng 7 cột chuẩn trên Cột Trái (Luồng Chuẩn Khuyến Nghị)
    if (yList) {
        yList.innerHTML = sourceLogs.map(item => {
            const isDanger = item.severity === "danger";
            const isWarn = item.severity === "warning";
            const badgeClass = isDanger ? "badge-danger" : (isWarn ? "badge-warning" : "badge-safe");
            const rowClass = isDanger ? "row-danger" : "";
            const predText = item.prediction_next_4s || "Duy trì ổn định 4s tới";
            const snapHtml = item.snapshot_url
                ? `<img src="${escapeHtml(item.snapshot_url)}" alt="${escapeHtml(item.action)}" class="snapshot-thumb" loading="lazy" onclick="openSnapshotModal('${escapeHtml(item.snapshot_url)}', '${escapeHtml(item.id || item.code)}', '${escapeHtml(item.action)}', '${escapeHtml(item.timestamp)}', '${escapeHtml(item.description)}', '${escapeHtml(predText)}')" />`
                : `<span class="mono text-muted">--</span>`;

            return `
                <tr class="${rowClass}">
                    <td><span class="log-code-badge">${escapeHtml(item.code || item.id)}</span></td>
                    <td class="mono">${escapeHtml(item.timestamp || "--:--:--")}</td>
                    <td>${getModelTierBadge(item.model_tier)}</td>
                    <td><span class="badge ${badgeClass}">${escapeHtml(item.action)}</span></td>
                    <td class="desc-cell">${escapeHtml(item.description)}</td>
                    <td class="prediction-cell">
                        <div class="prediction-badge">
                            <span class="pred-icon">${ICONS.sparkles}</span>
                            <span class="pred-text">${escapeHtml(predText)}</span>
                        </div>
                    </td>
                    <td style="text-align: center;">${snapHtml}</td>
                </tr>
            `;
        }).join("");
    }

    // Render Bảng 7 cột trên Cột Phải (Luồng Tùy Chỉnh Tài Nguyên)
    let zSafe = 0, zWarn = 0, zDanger = 0;
    if (zList) {
        zList.innerHTML = sourceLogs.map((item, idx) => {
            if (isOptimal) {
                if (item.severity === "danger") zDanger += 1;
                else if (item.severity === "warning") zWarn += 1;
                else zSafe += 1;

                const isDanger = item.severity === "danger";
                const isWarn = item.severity === "warning";
                const badgeClass = isDanger ? "badge-danger" : (isWarn ? "badge-warning" : "badge-safe");
                const predText = item.prediction_next_4s || "Duy trì ổn định 4s tới";
                const snapHtml = item.snapshot_url
                    ? `<img src="${escapeHtml(item.snapshot_url)}" alt="${escapeHtml(item.action)}" class="snapshot-thumb" loading="lazy" onclick="openSnapshotModal('${escapeHtml(item.snapshot_url)}', '${escapeHtml(item.id || item.code)}', '${escapeHtml(item.action)}', '${escapeHtml(item.timestamp)}', '${escapeHtml(item.description)}', '${escapeHtml(predText)}')" />`
                    : `<span class="mono text-muted">--</span>`;

                return `
                    <tr class="${isDanger ? "row-danger" : ""}">
                        <td><span class="log-code-badge">${escapeHtml(item.code || item.id)}</span></td>
                        <td class="mono">${escapeHtml(item.timestamp || "--:--:--")}</td>
                        <td>${getModelTierBadge(item.model_tier)}</td>
                        <td><span class="badge ${badgeClass}">${escapeHtml(item.action)}</span></td>
                        <td class="desc-cell">${escapeHtml(item.description)}</td>
                        <td class="prediction-cell">
                            <div class="prediction-badge">
                                <span class="pred-icon">${ICONS.sparkles}</span>
                                <span class="pred-text">${escapeHtml(predText)}</span>
                            </div>
                        </td>
                        <td style="text-align: center;">${snapHtml}</td>
                    </tr>
                `;
            }

            if (isOverProvisioned) {
                if (item.severity === "danger") zDanger += 1;
                else if (item.severity === "warning") zWarn += 1;
                else zSafe += 1;

                const isDanger = item.severity === "danger";
                const isWarn = item.severity === "warning";
                const badgeClass = isDanger ? "badge-danger" : (isWarn ? "badge-warning" : "badge-safe");
                const predText = item.prediction_next_4s || "Duy trì ổn định 4s tới";
                const snapHtml = item.snapshot_url
                    ? `<img src="${escapeHtml(item.snapshot_url)}" alt="${escapeHtml(item.action)}" class="snapshot-thumb" loading="lazy" onclick="openSnapshotModal('${escapeHtml(item.snapshot_url)}', '${escapeHtml(item.id || item.code)}', '${escapeHtml(item.action)}', '${escapeHtml(item.timestamp)}', '${escapeHtml(item.description)}', '${escapeHtml(predText)}')" />`
                    : `<span class="mono text-muted">--</span>`;

                return `
                    <tr class="${isDanger ? "row-danger" : ""}">
                        <td><span class="log-code-badge">${escapeHtml(item.code || item.id)}</span></td>
                        <td class="mono">${escapeHtml(item.timestamp || "--:--:--")} <span class="text-muted">(+${st.zLatencyMs}ms)</span></td>
                        <td>${getModelTierBadge(item.model_tier)}</td>
                        <td><span class="badge ${badgeClass}">${escapeHtml(item.action)}</span></td>
                        <td class="desc-cell">${escapeHtml(item.description)} <span style="color: var(--accent-amber);">[Không tăng độ chính xác · Tốn ${ramMb} MB]</span></td>
                        <td class="prediction-cell">
                            <div class="prediction-badge">
                                <span class="pred-icon">${ICONS.sparkles}</span>
                                <span class="pred-text">${escapeHtml(predText)} (+${st.zLatencyMs}ms)</span>
                            </div>
                        </td>
                        <td style="text-align: center;">${snapHtml}</td>
                    </tr>
                `;
            }

            // Trường hợp cấu hình tài nguyên sai lệch (isDegraded)
            let zSev = item.severity;
            let zAction = item.action;
            let zDesc = item.description;
            let zPred = item.prediction_next_4s || "";

            if (item.severity === "danger" || item.severity === "warning") {
                zSev = "safe";
                zAction = st.policy === "block_fifo"
                    ? "An toàn giả tạo (Trôi khung FIFO)"
                    : `Bỏ sót biến cố (Rơi ${st.zDropPct}% khung)`;
                zDesc = `Mất khung biến cố do N=${st.cap}, trễ ${st.delay}ms (${polText}); AI chỉ nhận khung tĩnh cũ.`;
                zPred = `Sai lệch dự báo (+${st.zLatencyMs}ms)`;
            } else {
                zSev = st.isStall ? "danger" : "warning";
                zAction = st.isStall
                    ? "Đình trệ hàng đợi"
                    : "Nhiễu góc nghiêng cột sống";
                zDesc = `Tụt còn ~${st.zFps} FPS (rơi ${st.zDropPct}% khung) làm đứt quãng chuỗi khớp xương.`;
                zPred = `Thiếu mẫu liên tiếp (+${st.zLatencyMs}ms)`;
            }

            if (zSev === "danger") zDanger += 1;
            else if (zSev === "warning") zWarn += 1;
            else zSafe += 1;

            const badgeClass = zSev === "danger" ? "badge-danger" : (zSev === "warning" ? "badge-warning" : "badge-safe");
            const laggedItem = sourceLogs[Math.min(sourceLogs.length - 1, idx + 1)] || item;
            const snapUrl = laggedItem.snapshot_url || item.snapshot_url;
            const snapHtml = snapUrl
                ? `<img src="${escapeHtml(snapUrl)}" alt="${escapeHtml(zAction)}" class="snapshot-thumb" style="filter: contrast(0.92) sepia(0.18); border: 1.5px solid var(--accent-amber);" loading="lazy" onclick="openSnapshotModal('${escapeHtml(snapUrl)}', '${escapeHtml(item.id || item.code)}', '${escapeHtml(zAction)}', '${escapeHtml(item.timestamp)}', '${escapeHtml(zDesc)}', '${escapeHtml(zPred)}')" title="Khung hình trễ +${st.zLatencyMs}ms" />`
                : `<span class="mono text-muted">--</span>`;

            return `
                <tr class="${zSev === "danger" ? "row-danger" : ""}">
                    <td><span class="log-code-badge">${escapeHtml(item.code || item.id)}</span></td>
                    <td class="mono">${escapeHtml(item.timestamp || "--:--:--")} <span style="color: var(--accent-amber);">+${st.zLatencyMs}ms</span></td>
                    <td>${getModelTierBadge("local_heuristic")}</td>
                    <td><span class="badge ${badgeClass}">${escapeHtml(zAction)}</span></td>
                    <td class="desc-cell">${escapeHtml(zDesc)}</td>
                    <td class="prediction-cell">
                        <div class="prediction-badge">
                            <span class="pred-icon">${ICONS.sparkles}</span>
                            <span class="pred-text">${escapeHtml(zPred)}</span>
                        </div>
                    </td>
                    <td style="text-align: center;">${snapHtml}</td>
                </tr>
            `;
        }).join("");
    }

    safeSetText("live-z-safe-count", String(zSafe));
    safeSetText("live-z-warn-count", String(zWarn));
    safeSetText("live-z-danger-count", String(zDanger));

    if (isOptimal || isOverProvisioned) {
        safeSetText("live-z-rep-ergo", baseErgoText);
    } else {
        const degradedErgo = Math.max(35, baseErgoNum - Math.round(st.zDropPct * 0.55) - (st.policy === "block_fifo" ? 16 : 6));
        safeSetText("live-z-rep-ergo", `${degradedErgo} / 100 (Lệch)`);
    }
}

function renderLiveParallelLoop() {
    if (!isLiveParallelActive) return;
    liveTickCounter += 1;

    const liveImg = document.getElementById("live-stream-img");
    const yCanvas = document.getElementById("live-split-y-canvas");
    const zCanvas = document.getElementById("live-split-z-canvas");
    const yOffline = document.getElementById("live-split-y-offline");
    const zOffline = document.getElementById("live-split-z-offline");
    const st = osBranchZState;

    const camOnline = Boolean(liveImg && liveImg.src && liveImg.src.includes("/api/stream/live") && liveImg.complete && liveImg.naturalWidth > 10);
    const fallbackSnap = !camOnline ? getLatestRealSnapshotElement() : null;
    const activeSource = camOnline ? liveImg : fallbackSnap;

    if (activeSource) {
        if (yOffline) yOffline.classList.add("hidden");
        if (zOffline) zOffline.classList.add("hidden");

        if (yCanvas) {
            const yCtx = yCanvas.getContext("2d");
            const w = yCanvas.width || 1280;
            const h = yCanvas.height || 720;
            drawImageContain(yCtx, activeSource, w, h);
            pushFrameToRingBuffer(liveRingBuffer, activeSource, w, h);
        }

        if (zCanvas) {
            const zCtx = zCanvas.getContext("2d");
            const w = zCanvas.width || 1280;
            const h = zCanvas.height || 720;
            const shouldRefreshZ = !st.isStall && (liveTickCounter % Math.max(1, st.zSkipStride) === 0);

            if (liveRingBuffer.length > 0) {
                if (shouldRefreshZ || liveTickCounter <= 3) {
                    const lagIdx = Math.max(0, liveRingBuffer.length - 1 - st.zLagSlots);
                    const chosen = liveRingBuffer[lagIdx] || liveRingBuffer[liveRingBuffer.length - 1];
                    zCtx.clearRect(0, 0, w, h);
                    zCtx.drawImage(chosen, 0, 0, w, h);
                } else {
                    const stuckFrame = liveRingBuffer[0] || activeSource;
                    zCtx.clearRect(0, 0, w, h);
                    drawImageContain(zCtx, stuckFrame, w, h);
                }
            } else {
                drawImageContain(zCtx, activeSource, w, h);
            }
            drawZDiagnosticWatermark(zCtx, w, h, st);
        }
    } else {
        if (yOffline) yOffline.classList.remove("hidden");
        if (zOffline) zOffline.classList.remove("hidden");
    }

    if (liveTickCounter % 30 === 1) {
        updateLiveParallelReportsAndLogs();
    }

    liveParallelAnimId = requestAnimationFrame(renderLiveParallelLoop);
}

function enterLiveParallelSplit() {
    const normalContainer = document.querySelector("#tab-live .live-full-container");
    const splitWorkspace = document.getElementById("live-parallel-workspace");
    if (!splitWorkspace) return;

    if (normalContainer) normalContainer.classList.add("hidden");
    closeTelemetryPanel();
    splitWorkspace.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });

    isLiveParallelActive = true;
    liveRingBuffer = [];
    liveTickCounter = 0;
    updateDualModeEvaluation(osBranchZState.cap, osBranchZState.delay, osBranchZState.policy);
    updateLiveParallelReportsAndLogs();

    if (liveParallelAnimId) cancelAnimationFrame(liveParallelAnimId);
    liveParallelAnimId = requestAnimationFrame(renderLiveParallelLoop);
}

function exitLiveParallelSplit() {
    isLiveParallelActive = false;
    if (liveParallelAnimId) {
        cancelAnimationFrame(liveParallelAnimId);
        liveParallelAnimId = null;
    }
    const normalContainer = document.querySelector("#tab-live .live-full-container");
    const splitWorkspace = document.getElementById("live-parallel-workspace");
    if (splitWorkspace) splitWorkspace.classList.add("hidden");
    if (normalContainer) normalContainer.classList.remove("hidden");
}

// ==============================================================================
// TAB 2 (IMPORT VIDEO): FULL-PAGE 50/50 PARALLEL SPLIT-SCREEN ENGINE
// ==============================================================================
function populateVideoParallelSplitView() {
    const st = osBranchZState;
    const ramMb = ((st.cap * 1280 * 720 * 3) / (1024 * 1024)).toFixed(2);
    const polText = st.policy === "drop_oldest" ? "Priority" : "Block-FIFO";
    const isOptimal = (st.cap === 16 && st.delay === 0 && st.policy === "drop_oldest");
    const isOverProvisioned = (st.cap > 16 && st.delay === 0 && st.policy === "drop_oldest");

    safeSetText("split-vid-z-config-text", `N = ${st.cap} (${ramMb} MB) · ${st.delay} ms · ${polText}`);
    safeSetText("split-vid-z-fps", `${st.zFps} FPS`);
    safeSetText("split-vid-z-drop", `${st.zDropPct}%`);
    safeSetText("split-vid-z-ram", `${ramMb} MB`);

    // 1. Gán nguồn video đã dán nhãn cho #split-vid-y-player
    const srcPlayer = document.getElementById("result-annotated-video") || document.getElementById("result-orig-video");
    const yPlayer = document.getElementById("split-vid-y-player");
    if (yPlayer && srcPlayer && srcPlayer.src && yPlayer.src !== srcPlayer.src) {
        yPlayer.src = srcPlayer.src;
        yPlayer.currentTime = srcPlayer.currentTime || 0;
    }

    // 2. Vẽ thanh Timeline Heatmap cho Cột Trái và Cột Phải
    const yHm = document.getElementById("split-vid-y-heatmap");
    const zHm = document.getElementById("split-vid-z-heatmap");
    const hmData = (typeof currentHeatmapData !== "undefined" && Array.isArray(currentHeatmapData) && currentHeatmapData.length > 0)
        ? currentHeatmapData
        : [
            { time: 0, time_str: "00:00", score: 1.2, level: "safe" },
            { time: 3, time_str: "00:03", score: 8.8, level: "danger" },
            { time: 6, time_str: "00:06", score: 5.4, level: "warning" },
            { time: 9, time_str: "00:09", score: 1.0, level: "safe" }
        ];

    if (yHm) {
        yHm.innerHTML = "";
        hmData.forEach((slot) => {
            const c = document.createElement("div");
            c.className = `heatmap-cell ${slot.level || "safe"}`;
            c.title = `[Luồng Chuẩn · ${slot.time_str}] Điểm: ${slot.score}`;
            c.onclick = () => {
                if (yPlayer) yPlayer.currentTime = slot.time || 0;
            };
            yHm.appendChild(c);
        });
    }

    if (zHm) {
        zHm.innerHTML = "";
        hmData.forEach((slot, idx) => {
            const c = document.createElement("div");
            const level = slot.level || "safe";
            const isRisk = (level === "danger" || level === "warning" || parseFloat(slot.score || 0) >= 4.0);
            const isDropped = (
                (st.policy === "block_fifo" && isRisk && idx < Math.floor(hmData.length * 0.68)) ||
                ((st.cap < 16 || st.delay > 0) && ((idx + 1) % (st.delay >= 80 ? 2 : 3) === 0))
            );
            const extra = isDropped ? "heatmap-segment seg-z-dropped" : (st.cap > 16 ? "heatmap-segment seg-z-delayed" : "");
            c.className = `heatmap-cell ${level} ${extra}`.trim();
            c.title = isDropped
                ? `[Luồng Tùy Chỉnh · ${slot.time_str}] Mất mẫu do cấu hình tài nguyên`
                : `[Luồng Tùy Chỉnh · ${slot.time_str}] Điểm: ${slot.score}`;
            c.onclick = () => {
                if (yPlayer) yPlayer.currentTime = slot.time || 0;
            };
            zHm.appendChild(c);
        });
    }

    // 3. Tổng hợp Báo cáo AI & Bảng phân đoạn cho Cột Trái và Cột Phải (0 Token phát sinh!)
    const res = (typeof currentAnalysisResult !== "undefined" && currentAnalysisResult) ? currentAnalysisResult : {};
    const gem = res.gemini_report || {};
    const segs = (typeof currentSegments !== "undefined" && Array.isArray(currentSegments) && currentSegments.length > 0)
        ? currentSegments
        : [
            { segment_id: "#SEG-01", time_range: "00:00 - 00:04", scene_summary: "Các đối tượng di chuyển vào vị trí, xuất hiện va chạm động học.", danger_score: 8.6, severity: "danger" },
            { segment_id: "#SEG-02", time_range: "00:04 - 00:08", scene_summary: "Tương tác đối kháng trực diện, gia tốc vượt ngưỡng an toàn.", danger_score: 9.1, severity: "danger" },
            { segment_id: "#SEG-03", time_range: "00:08 - 00:12", scene_summary: "Các đối tượng tách ra và ổn định lại tư thế.", danger_score: 2.0, severity: "safe" }
        ];

    const yThreatText = document.getElementById("rep-threat-level") ? document.getElementById("rep-threat-level").textContent : (gem.threat_level || "NGUY HIỂM");
    const yThreatClass = (document.getElementById("rep-threat-level") ? document.getElementById("rep-threat-level").className : "badge badge-danger").replace(/\bmono\b/g, "").trim();
    const yIncident = gem.primary_incident || res.peak_danger_reason || "Phát hiện xung đột thể chất cường độ cao";
    const yDiagnosis = gem.detailed_diagnosis || "Ghi nhận đầy đủ các khung hình đỉnh điểm và xác định chính xác thời điểm va chạm.";
    const yRec = gem.recommended_action || "Lưu trữ trích đoạn bằng chứng và kiểm tra an ninh tại khu vực.";

    const yThreatBadge = document.getElementById("split-y-rep-threat");
    if (yThreatBadge) {
        yThreatBadge.textContent = yThreatText;
        yThreatBadge.className = yThreatClass;
    }
    safeSetText("split-y-rep-incident", yIncident);
    safeSetText("split-y-rep-diagnosis", yDiagnosis);
    safeSetText("split-y-rep-rec", yRec);

    // Render Bảng 4 cột chuẩn trên Cột Trái (#split-y-segments-list)
    const ySegContainer = document.getElementById("split-y-segments-list");
    if (ySegContainer) {
        ySegContainer.innerHTML = segs.map(s => {
            const numScore = parseFloat(s.danger_score || 0);
            const isDanger = numScore >= 8.0 || s.severity === "danger";
            const isWarn = !isDanger && (numScore >= 4.0 || s.severity === "warning");
            const badgeClass = isDanger ? "badge badge-danger" : (isWarn ? "badge badge-warning" : "badge badge-safe");
            const badgeText = isDanger ? "NGUY HIỂM" : (isWarn ? "CẢNH BÁO" : "AN TOÀN");
            const threatPillClass = isDanger ? "threat-pill-danger" : (isWarn ? "threat-pill-warn" : "threat-pill-safe");
            const summaryText = s.scene_summary || s.context_description || "Hoạt động ổn định trong phân đoạn.";
            const snapHtml = s.snapshot_url
                ? `<img src="${escapeHtml(s.snapshot_url)}" class="seg-snapshot-thumb" onclick="openSnapshotModal('${escapeHtml(s.snapshot_url)}', '${escapeHtml(s.segment_id)}', '${escapeHtml(summaryText)}', '${escapeHtml(s.time_range)}', '${escapeHtml(summaryText)}', '')" />`
                : `<span class="mono text-muted">--</span>`;

            return `
                <tr>
                    <td>
                        <div class="seg-range-badge mono">${escapeHtml(s.time_range || "")}</div>
                        <div class="seg-id-sub mono">${escapeHtml(s.segment_id || "")}</div>
                    </td>
                    <td>
                        <div class="seg-summary-line">${escapeHtml(summaryText)}</div>
                    </td>
                    <td>
                        <div class="threat-header-row">
                            <span class="${badgeClass}">${badgeText}</span>
                            <div class="threat-score-pill mono ${threatPillClass}">${numScore.toFixed(1)} <span class="threat-scale">/ 10</span></div>
                        </div>
                    </td>
                    <td style="text-align: center;">${snapHtml}</td>
                </tr>
            `;
        }).join("");
    }

    // 4. Render Bảng 4 cột trên Cột Phải (#split-z-segments-list) phản ánh hệ quả cấu hình tài nguyên
    let droppedHighRiskCount = 0;
    let survivingMaxScore = 0.0;
    const zSegContainer = document.getElementById("split-z-segments-list");
    const calmFallbackSnap = segs[segs.length - 1]?.snapshot_url || segs[0]?.snapshot_url || "";

    const zSegHtml = segs.map((s, idx) => {
        const numScore = parseFloat(s.danger_score || 0);
        const isDanger = numScore >= 8.0 || s.severity === "danger";
        const isWarn = !isDanger && (numScore >= 4.0 || s.severity === "warning");
        const summaryText = s.scene_summary || s.context_description || "Hoạt động ổn định trong phân đoạn.";

        if (isOptimal) {
            if (numScore > survivingMaxScore) survivingMaxScore = numScore;
            const badgeClass = isDanger ? "badge badge-danger" : (isWarn ? "badge badge-warning" : "badge badge-safe");
            const badgeText = isDanger ? "NGUY HIỂM" : (isWarn ? "CẢNH BÁO" : "AN TOÀN");
            const threatPillClass = isDanger ? "threat-pill-danger" : (isWarn ? "threat-pill-warn" : "threat-pill-safe");
            const snapHtml = s.snapshot_url
                ? `<img src="${escapeHtml(s.snapshot_url)}" class="seg-snapshot-thumb" onclick="openSnapshotModal('${escapeHtml(s.snapshot_url)}', '${escapeHtml(s.segment_id)}', '${escapeHtml(summaryText)}', '${escapeHtml(s.time_range)}', '${escapeHtml(summaryText)}', '')" />`
                : `<span class="mono text-muted">--</span>`;

            return `
                <tr>
                    <td>
                        <div class="seg-range-badge mono">${escapeHtml(s.time_range || "")}</div>
                        <div class="seg-id-sub mono">${escapeHtml(s.segment_id || "")}</div>
                    </td>
                    <td><div class="seg-summary-line">${escapeHtml(summaryText)}</div></td>
                    <td>
                        <div class="threat-header-row">
                            <span class="${badgeClass}">${badgeText}</span>
                            <div class="threat-score-pill mono ${threatPillClass}">${numScore.toFixed(1)} <span class="threat-scale">/ 10</span></div>
                        </div>
                    </td>
                    <td style="text-align: center;">${snapHtml}</td>
                </tr>
            `;
        }

        if (isOverProvisioned) {
            if (numScore > survivingMaxScore) survivingMaxScore = numScore;
            const badgeClass = isDanger ? "badge badge-danger" : (isWarn ? "badge badge-warning" : "badge badge-safe");
            const badgeText = isDanger ? "NGUY HIỂM" : (isWarn ? "CẢNH BÁO" : "AN TOÀN");
            const threatPillClass = isDanger ? "threat-pill-danger" : (isWarn ? "threat-pill-warn" : "threat-pill-safe");
            const snapHtml = s.snapshot_url
                ? `<img src="${escapeHtml(s.snapshot_url)}" class="seg-snapshot-thumb" onclick="openSnapshotModal('${escapeHtml(s.snapshot_url)}', '${escapeHtml(s.segment_id)}', '${escapeHtml(summaryText)}', '${escapeHtml(s.time_range)}', '${escapeHtml(summaryText)}', '')" />`
                : `<span class="mono text-muted">--</span>`;

            return `
                <tr>
                    <td>
                        <div class="seg-range-badge mono">${escapeHtml(s.time_range || "")}</div>
                        <div class="seg-id-sub mono">${escapeHtml(s.segment_id || "")} · +${st.zLatencyMs}ms</div>
                    </td>
                    <td>
                        <div class="seg-summary-line">${escapeHtml(summaryText)} <span class="text-muted">(Trễ +${st.zLatencyMs}ms · ${ramMb} MB RAM)</span></div>
                    </td>
                    <td>
                        <div class="threat-header-row">
                            <span class="${badgeClass}">${badgeText}</span>
                            <div class="threat-score-pill mono ${threatPillClass}">${numScore.toFixed(1)} <span class="threat-scale">/ 10</span></div>
                        </div>
                    </td>
                    <td style="text-align: center;">${snapHtml}</td>
                </tr>
            `;
        }

        const evictedByFifo = (st.policy === "block_fifo" && (isDanger || isWarn) && idx < Math.max(1, segs.length - 1));
        const droppedByQueue = ((st.delay >= 30 || st.cap < 12) && (isDanger || isWarn || idx % 2 === 0));
        const isMisdiagnosed = evictedByFifo || droppedByQueue;

        if (isMisdiagnosed) {
            if (isDanger || isWarn) droppedHighRiskCount += 1;
            const wrongScore = isDanger ? 1.8 : 1.2;
            if (wrongScore > survivingMaxScore) survivingMaxScore = wrongScore;

            const wrongReason = evictedByFifo
                ? `Mất mẫu đỉnh điểm do trục xuất FIFO; AI nhận nhầm khung tĩnh cuối video.`
                : `Rơi ${st.zDropPct}% khung hình (N=${st.cap}, trễ ${st.delay}ms); điểm rủi ro tụt từ ${numScore.toFixed(1)} xuống ${wrongScore.toFixed(1)}/10.`;

            const wrongSnap = calmFallbackSnap || s.snapshot_url;
            const snapHtml = wrongSnap
                ? `<img src="${escapeHtml(wrongSnap)}" class="seg-snapshot-thumb" style="filter: grayscale(0.45) contrast(0.88); border: 1.5px solid var(--accent-crimson);" title="Khung hình bị lệch mẫu" onclick="openSnapshotModal('${escapeHtml(wrongSnap)}', '${escapeHtml(s.segment_id)}', 'Nhận diện sai lệch', '${escapeHtml(s.time_range)}', '${escapeHtml(wrongReason)}', '')" />`
                : `<span class="mono text-muted">Mất khung</span>`;

            return `
                <tr>
                    <td>
                        <div class="seg-range-badge mono">${escapeHtml(s.time_range || "")}</div>
                        <div class="seg-id-sub" style="color: var(--accent-crimson); font-weight: 600;">${escapeHtml(s.segment_id || "")} · LỆCH MẪU</div>
                    </td>
                    <td>
                        <div class="seg-summary-line" style="color: var(--accent-amber-text);">${escapeHtml(wrongReason)}</div>
                    </td>
                    <td>
                        <div class="threat-header-row">
                            <span class="badge badge-safe">AN TOÀN GIẢ TẠO</span>
                            <div class="threat-score-pill mono threat-pill-safe">${wrongScore.toFixed(1)} <span class="threat-scale">/ 10</span></div>
                        </div>
                    </td>
                    <td style="text-align: center;">${snapHtml}</td>
                </tr>
            `;
        }

        const degradedScore = Math.max(1.0, Number((numScore * 0.65).toFixed(1)));
        if (degradedScore > survivingMaxScore) survivingMaxScore = degradedScore;
        const snapHtml = s.snapshot_url
            ? `<img src="${escapeHtml(s.snapshot_url)}" class="seg-snapshot-thumb" onclick="openSnapshotModal('${escapeHtml(s.snapshot_url)}', '${escapeHtml(s.segment_id)}', '${escapeHtml(summaryText)}', '${escapeHtml(s.time_range)}', '${escapeHtml(summaryText)}', '')" />`
            : `<span class="mono text-muted">--</span>`;

        return `
            <tr>
                <td>
                    <div class="seg-range-badge mono">${escapeHtml(s.time_range || "")}</div>
                    <div class="seg-id-sub mono">${escapeHtml(s.segment_id || "")} · +${st.zLatencyMs}ms</div>
                </td>
                <td>
                    <div class="seg-summary-line">${escapeHtml(summaryText)} <span style="color: var(--accent-amber);">(~${st.zFps} FPS)</span></div>
                </td>
                <td>
                    <div class="threat-header-row">
                        <span class="badge badge-warning">SUY GIẢM MẪU</span>
                        <div class="threat-score-pill mono threat-pill-warn">${degradedScore.toFixed(1)} <span class="threat-scale">/ 10</span></div>
                    </div>
                </td>
                <td style="text-align: center;">${snapHtml}</td>
            </tr>
        `;
    }).join("");

    if (zSegContainer) zSegContainer.innerHTML = zSegHtml;

    const totalRiskSegs = segs.filter(s => parseFloat(s.danger_score || 0) >= 4.0 || s.severity === "danger" || s.severity === "warning").length;
    const retentionPct = totalRiskSegs > 0
        ? Math.max(0, Math.round(((totalRiskSegs - droppedHighRiskCount) / totalRiskSegs) * 100))
        : (isOptimal || isOverProvisioned ? 100 : Math.max(20, Math.round(100 - st.zDropPct)));
    const ramRatio = (st.cap / 16.0).toFixed(1);

    safeSetText("vod-retention-val", `${retentionPct}% (${droppedHighRiskCount > 0 ? `Bỏ sót ${droppedHighRiskCount} biến cố` : "Bảo toàn đầy đủ"})`);
    safeSetText("vod-ram-diff-val", `${ramMb} MB / 42.19 MB (${ramRatio}x)`);

    const zThreatBadge = document.getElementById("split-z-rep-threat");
    if (isOptimal) {
        if (zThreatBadge) {
            zThreatBadge.textContent = `${yThreatText} (CHUẨN 100%)`;
            zThreatBadge.className = yThreatClass;
        }
        safeSetText("split-z-rep-incident", yIncident);
        safeSetText("split-z-rep-diagnosis", yDiagnosis);
        safeSetText("split-z-rep-rec", yRec);
        safeSetText("vod-verdict-text", "Đạt điểm cân bằng tối ưu: Bảo toàn 100% khung hình đỉnh điểm với 42.19 MB RAM.");
    } else if (isOverProvisioned) {
        if (zThreatBadge) {
            zThreatBadge.textContent = `${yThreatText} (DƯ ${ramRatio}x RAM)`;
            zThreatBadge.className = "badge badge-warning";
        }
        safeSetText("split-z-rep-incident", `${yIncident} (Tốn ${ramMb} MB RAM, không tăng độ chính xác)`);
        safeSetText("split-z-rep-diagnosis", yDiagnosis);
        safeSetText("split-z-rep-rec", `Cấp phát N=${st.cap} gây trễ hàng đợi +${st.zLatencyMs}ms mà không phát hiện thêm biến cố nào.`);
        safeSetText("vod-verdict-text", `Tăng bộ đệm lên N=${st.cap} tiêu tốn gấp ${ramRatio}x RAM nhưng chất lượng giữ nguyên.`);
    } else if (droppedHighRiskCount > 0) {
        if (zThreatBadge) {
            zThreatBadge.textContent = "SAI LỆCH (ÂM TÍNH GIẢ)";
            zThreatBadge.className = "badge badge-danger";
        }
        safeSetText("split-z-rep-incident", `Bỏ sót ${droppedHighRiskCount} phân đoạn nguy hiểm (Điểm tối đa tụt còn ${survivingMaxScore.toFixed(1)}/10)`);
        safeSetText(
            "split-z-rep-diagnosis",
            st.policy === "block_fifo"
                ? "Chính sách FIFO làm khung hình tĩnh cuối video ghi đè mất các khung hình xung đột đỉnh điểm trong RAM."
                : `Độ trễ ${st.delay}ms và bộ đệm N=${st.cap} làm rơi ${st.zDropPct}% khung hình (~${st.zFps} FPS), gây đứt gãy khoảnh khắc va chạm.`
        );
        safeSetText("split-z-rep-rec", "Nhấn 'Chuẩn Khuyến Nghị (N=16 · 0ms)' ở thanh phía trên để khôi phục 100% biến cố.");
        safeSetText("vod-verdict-text", `Cấu hình lệch chuẩn làm mất ${droppedHighRiskCount} phân đoạn quan trọng.`);
    } else {
        if (zThreatBadge) {
            zThreatBadge.textContent = `SUY GIẢM (+${st.zLatencyMs}ms)`;
            zThreatBadge.className = "badge badge-warning";
        }
        safeSetText("split-z-rep-incident", `${yIncident} (Trễ hàng đợi +${st.zLatencyMs}ms)`);
        safeSetText("split-z-rep-diagnosis", `Tốc độ giảm còn ~${st.zFps} FPS (rơi ${st.zDropPct}% khung hình), làm giảm độ chính xác vận tốc.`);
        safeSetText("split-z-rep-rec", "Khôi phục cấu hình chuẩn (N=16 · 0ms · Priority) để đạt 30.0 FPS.");
        safeSetText("vod-verdict-text", `Tốc độ suy giảm còn ~${st.zFps} FPS, trễ +${st.zLatencyMs}ms.`);
    }
}

function renderVideoParallelLoop() {
    if (!isVideoParallelActive) return;
    videoTickCounter += 1;

    const yPlayer = document.getElementById("split-vid-y-player");
    const fallbackPlayer = document.getElementById("result-annotated-video") || document.getElementById("result-orig-video");
    const zCanvas = document.getElementById("split-vid-z-canvas");
    const st = osBranchZState;

    if (zCanvas) {
        const zCtx = zCanvas.getContext("2d");
        const w = zCanvas.width || 1280;
        const h = zCanvas.height || 720;
        const activeVideoEl = (yPlayer && yPlayer.readyState >= 2) ? yPlayer : ((fallbackPlayer && fallbackPlayer.readyState >= 2) ? fallbackPlayer : null);

        if (activeVideoEl) {
            if (!activeVideoEl.paused || videoRingBuffer.length === 0) {
                pushFrameToRingBuffer(videoRingBuffer, activeVideoEl, w, h);
            }
            const shouldRefreshZ = !st.isStall && (videoTickCounter % Math.max(1, st.zSkipStride) === 0);
            if (videoRingBuffer.length > 0) {
                if (shouldRefreshZ || activeVideoEl.paused || videoTickCounter <= 3) {
                    const lagIdx = Math.max(0, videoRingBuffer.length - 1 - st.zLagSlots);
                    const chosen = videoRingBuffer[lagIdx] || videoRingBuffer[videoRingBuffer.length - 1];
                    zCtx.clearRect(0, 0, w, h);
                    zCtx.drawImage(chosen, 0, 0, w, h);
                } else {
                    const stuckFrame = videoRingBuffer[0] || activeVideoEl;
                    zCtx.clearRect(0, 0, w, h);
                    drawImageContain(zCtx, stuckFrame, w, h);
                }
            } else {
                drawImageContain(zCtx, activeVideoEl, w, h);
            }
            drawZDiagnosticWatermark(zCtx, w, h, st);
        } else {
            const snapFallback = getLatestRealSnapshotElement();
            if (snapFallback) {
                drawImageContain(zCtx, snapFallback, w, h);
            }
            drawZDiagnosticWatermark(zCtx, w, h, st);
        }
    }

    videoParallelAnimId = requestAnimationFrame(renderVideoParallelLoop);
}

function enterVideoParallelSplit() {
    const splitWorkspace = document.getElementById("video-parallel-workspace");
    if (!splitWorkspace) return;

    const importCard = document.querySelector("#tab-video .import-card");
    const timelineSec = document.getElementById("timeline-section");
    const trimmerSec = document.getElementById("trimmer-section");
    const procSec = document.getElementById("processing-section");
    const resSec = document.getElementById("results-section");

    if (importCard) importCard.classList.add("hidden");
    if (timelineSec) timelineSec.classList.add("hidden");
    if (trimmerSec) trimmerSec.classList.add("hidden");
    if (procSec) procSec.classList.add("hidden");
    if (resSec) resSec.classList.add("hidden");

    splitWorkspace.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });

    isVideoParallelActive = true;
    videoRingBuffer = [];
    videoTickCounter = 0;
    updateDualModeEvaluation(osBranchZState.cap, osBranchZState.delay, osBranchZState.policy);
    populateVideoParallelSplitView();

    const yPlayer = document.getElementById("split-vid-y-player");
    if (yPlayer && yPlayer.src) {
        yPlayer.play().catch(() => {});
    }

    if (videoParallelAnimId) cancelAnimationFrame(videoParallelAnimId);
    videoParallelAnimId = requestAnimationFrame(renderVideoParallelLoop);
}

function exitVideoParallelSplit() {
    isVideoParallelActive = false;
    if (videoParallelAnimId) {
        cancelAnimationFrame(videoParallelAnimId);
        videoParallelAnimId = null;
    }
    const yPlayer = document.getElementById("split-vid-y-player");
    if (yPlayer && !yPlayer.paused) yPlayer.pause();

    const splitWorkspace = document.getElementById("video-parallel-workspace");
    if (splitWorkspace) splitWorkspace.classList.add("hidden");

    const importCard = document.querySelector("#tab-video .import-card");
    const timelineSec = document.getElementById("timeline-section");
    const resSec = document.getElementById("results-section");
    if (importCard) importCard.classList.remove("hidden");
    if (timelineSec && typeof currentVideoData !== "undefined" && currentVideoData) {
        timelineSec.classList.remove("hidden");
    }
    if (resSec) resSec.classList.remove("hidden");
}

function toggleSplitVideoPlayback() {
    const yPlayer = document.getElementById("split-vid-y-player");
    if (!yPlayer) return;
    if (yPlayer.paused) {
        yPlayer.play().catch(() => {});
    } else {
        yPlayer.pause();
    }
}

function restartSplitVideoPlayback() {
    const yPlayer = document.getElementById("split-vid-y-player");
    if (!yPlayer) return;
    videoRingBuffer = [];
    yPlayer.currentTime = 0;
    yPlayer.play().catch(() => {});
}

function renderHeatmapZTrack(heatmapData, totalDuration) {
    const zBar = document.getElementById("timeline-heatmap-bar-z");
    if (!zBar) return;
    zBar.innerHTML = "";
}

// ==============================================================================
// GLOBAL WINDOW BINDINGS
// ==============================================================================
window.switchTab = switchTab;
window.toggleCamera = toggleCamera;
window.toggleCameraEnhancer = toggleCameraEnhancer;
window.captureManualSnapshot = captureManualSnapshot;
window.clearLogs = clearLogs;
window.exportLogsToCSV = exportLogsToCSV;
window.openSnapshotModal = openSnapshotModal;
window.closeSnapshotModal = closeSnapshotModal;
window.openLivePipelineModal = openLivePipelineModal;
window.closeLivePipelineModal = closeLivePipelineModal;
window.previewConveyorFrame = previewConveyorFrame;
window.releaseConveyorFrame = releaseConveyorFrame;
window.setFlipbookSpeed = setFlipbookSpeed;
window.toggleFlipbookOnionSkin = toggleFlipbookOnionSkin;
window.switchSourceMode = switchSourceMode;
window.handleFileSelected = handleFileSelected;
window.handleURLImport = handleURLImport;
window.loadSampleVideo = loadSampleVideo;
window.resetDropzoneUI = resetDropzoneUI;
window.applyPreset = applyPreset;
window.onRangeStartChange = onRangeStartChange;
window.onRangeEndChange = onRangeEndChange;
window.launchProcessing = launchProcessing;
window.focusTimelineSegment = focusTimelineSegment;
window.toggleLoopCurrentSegment = toggleLoopCurrentSegment;
window.clearSegmentFocus = clearSegmentFocus;
window.filterByEntity = filterByEntity;
window.sendChatMessage = sendChatMessage;
window.confirmURLRangeExtract = confirmURLRangeExtract;
window.setSlicePreset = setSlicePreset;
window.renderExecutiveSceneNarrative = renderExecutiveSceneNarrative;
window.renderBehaviorAnalytics = renderBehaviorAnalytics;
window.seekBothPlayers = seekBothPlayers;
window.toggleTelemetryDrawer = toggleTelemetryDrawer;
window.toggleInlineTelemetryPanel = toggleInlineTelemetryPanel;
window.closeTelemetryPanel = closeTelemetryPanel;
window.onOSLabSliderInput = onOSLabSliderInput;
window.commitOSLabConfig = commitOSLabConfig;
window.applyOSLabPreset = applyOSLabPreset;
window.triggerOSLabStressBurst = triggerOSLabStressBurst;
window.resetOSLabCounters = resetOSLabCounters;
window.renderOSPipelineReport = renderOSPipelineReport;
window.toggleTheme = toggleTheme;
window.setTheme = setTheme;
window.initTheme = initTheme;
window.drawMultiTrackActorTimeline = drawMultiTrackActorTimeline;
window.drawEventCentricFlowStreams = drawEventCentricFlowStreams;
window.getSegmentMilestoneTitle = getSegmentMilestoneTitle;
window.updateEventFlowPlayhead = updateEventFlowPlayhead;
window.showEventFlowTooltip = showEventFlowTooltip;
window.hideEventFlowTooltip = hideEventFlowTooltip;

window.openOSExperimentModal = openOSExperimentModal;
window.closeOSExperimentModal = closeOSExperimentModal;
window.switchLabScenario = switchLabScenario;
window.applyLabBufferPreset = applyLabBufferPreset;
window.setLabBufferPolicy = setLabBufferPolicy;
window.onLabBufferKnobChange = onLabBufferKnobChange;
window.triggerLabDeadlock = triggerLabDeadlock;
window.resolveLabDeadlock = resolveLabDeadlock;
window.runLabMemorySim = runLabMemorySim;

window.updateDualModeEvaluation = updateDualModeEvaluation;
window.simulateControlledStall = simulateControlledStall;
window.resetToHardwareOptimal = resetToHardwareOptimal;
window.runOSLiveBenchmark = runOSLiveBenchmark;
window.applySplitResourcePreset = applySplitResourcePreset;

window.onOSLabPolicyChange = onOSLabPolicyChange;
window.onVideoZControlInput = onVideoZControlInput;
window.applyVideoZUnderProvisionPreset = applyVideoZUnderProvisionPreset;
window.renderHeatmapZTrack = renderHeatmapZTrack;

window.enterLiveParallelSplit = enterLiveParallelSplit;
window.exitLiveParallelSplit = exitLiveParallelSplit;
window.enterVideoParallelSplit = enterVideoParallelSplit;
window.exitVideoParallelSplit = exitVideoParallelSplit;
window.toggleSplitVideoPlayback = toggleSplitVideoPlayback;
window.restartSplitVideoPlayback = restartSplitVideoPlayback;
window.populateVideoParallelSplitView = populateVideoParallelSplitView;
window.selectPreflightZPreset = selectPreflightZPreset;
window.syncPreflightZInputs = syncPreflightZInputs;
