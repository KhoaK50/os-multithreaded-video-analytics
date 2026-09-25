/**
 * CYBER SURVEILLANCE HUB - CLIENT LOGIC
 * Tích hợp Live Camera 30 FPS, CapCut Timeline Trimmer, Token Meter & Semantic Q&A.
 */

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
let currentSegments = [];
let currentHeatmapData = [];
let allEntitiesDetected = [];
let activeFocusSegment = null;
let isLoopingSegment = false;
let activeEntityFilter = 'all';

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
    if (currentTab !== "live") return;
    try {
        const res = await fetch("/api/telemetry");
        if (!res.ok) return;
        const data = await res.json();

        if (!isServerOnline) {
            isServerOnline = true;
            console.info("[+] Đã kết nối lại máy chủ FastAPI thành công.");
        }

        // Cập nhật OS Metrics an toàn tuyệt đối
        safeSetText("live-fps", `${data.fps || 0} FPS`);
        safeSetText("live-cpu", `${data.cpu_percent || 0}%`);
        safeSetText("live-vram", `${data.gpu_vram_mb || 0} / ${data.gpu_vram_total_mb || 8192} MB`);
        safeSetText("live-ram", `${data.ram_percent || 0}%`);

        // Cập nhật Biomechanics
        const bio = data.biomechanics || {};
        const isDanger = bio.is_danger;
        const threatBadge = document.getElementById("live-threat-badge");
        if (threatBadge) {
            threatBadge.className = isDanger ? "badge badge-danger" : "badge badge-safe";
            threatBadge.textContent = isDanger ? "🔴 NGUY HIỂM" : "● AN TOÀN";
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

        // Update camera offline overlay & status pills
        const offlineOverlay = document.getElementById("cam-offline-overlay");
        const toggleBtn = document.getElementById("btn-toggle-cam");
        const statusDot = document.getElementById("live-stream-status-dot");

        if (data.camera_running) {
            if (offlineOverlay) offlineOverlay.classList.add("hidden");
            if (toggleBtn) {
                toggleBtn.textContent = "⏹️ Tạm dừng Camera";
                toggleBtn.className = "btn btn-sm btn-danger-outline";
            }
            if (statusDot) {
                statusDot.style.background = "var(--accent-emerald)";
                statusDot.style.boxShadow = "0 0 8px var(--accent-emerald)";
            }
            safeSetText("live-stream-status-text", `TRỰC TIẾP (${Math.round(data.fps || 30)} FPS)`);
        } else {
            if (offlineOverlay) offlineOverlay.classList.remove("hidden");
            if (toggleBtn) {
                toggleBtn.textContent = "▶️ Khởi động Camera";
                toggleBtn.className = "btn btn-sm btn-primary";
            }
            if (statusDot) {
                statusDot.style.background = "var(--accent-crimson)";
                statusDot.style.boxShadow = "0 0 8px var(--accent-crimson)";
            }
            safeSetText("live-stream-status-text", "ĐANG TẠM DỪNG");
        }
    } catch (e) {
        if (isServerOnline) {
            isServerOnline = false;
            console.warn("[!] Máy chủ FastAPI (127.0.0.1:8000) đang ngắt kết nối hoặc đang khởi động lại.");
            safeSetText("live-stream-status-text", "MÁY CHỦ CHƯA BẬT (Chạy: python main.py)");
            const statusDot = document.getElementById("live-stream-status-dot");
            if (statusDot) {
                statusDot.style.background = "var(--accent-amber)";
                statusDot.style.boxShadow = "0 0 8px var(--accent-amber)";
            }
        }
    }
}

async function toggleCamera(forceAction = null) {
    const toggleBtn = document.getElementById("btn-toggle-cam");
    let action = forceAction;
    if (!action) {
        action = (toggleBtn && toggleBtn.textContent.includes("Tạm dừng")) ? "stop" : "start";
    }

    try {
        const res = await fetch(`/api/camera/toggle?action=${action}`, { method: "POST" });
        await fetchTelemetry();
        if (action === "start") {
            const img = document.getElementById("live-stream-img");
            if (img) img.src = "/api/stream/live?t=" + Date.now();
        }
    } catch (e) {
        console.error("Lỗi điều khiển camera:", e);
    }
}

// Quản lý Webcam Trình Duyệt (HTML5 getUserMedia)
let browserCamStream = null;
let browserCamInterval = null;
let isStreamingBrowserCam = false;

async function toggleBrowserWebcam() {
    const btn = document.getElementById("btn-browser-cam");
    if (isStreamingBrowserCam) {
        stopBrowserWebcam();
        return;
    }

    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert("Trình duyệt không hỗ trợ hoặc đang chặn quyền truy cập Camera. Hãy đảm bảo bạn truy cập qua link HTTPS hoặc localhost và đã bấm 'Cho phép (Allow)'.");
            return;
        }

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
        if (btn) {
            btn.textContent = "⏹ Tắt Webcam Trình Duyệt";
            btn.classList.add("active-toggle");
            btn.classList.remove("btn-primary");
            btn.classList.add("btn-danger-outline");
        }

        // Tự động kết nối lại luồng stream hiển thị
        const liveImg = document.getElementById("live-stream-img");
        if (liveImg) {
            liveImg.src = "/api/stream/live?t=" + Date.now();
        }
        const offlineOverlay = document.getElementById("cam-offline-overlay");
        if (offlineOverlay) offlineOverlay.classList.add("hidden");

        // Bắt đầu vòng lặp gửi khung hình thông minh (Adaptive Ping-Pong - Chống Nghẽn Mạng Tuyệt Đối)
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
        alert("Không thể mở camera thiết bị: " + (err.message || "Bị từ chối quyền truy cập"));
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
    const btn = document.getElementById("btn-browser-cam");
    if (btn) {
        btn.textContent = "🌐 Bật Webcam Trình Duyệt";
        btn.classList.remove("active-toggle");
        btn.classList.remove("btn-danger-outline");
        btn.classList.add("btn-primary");
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
        mirrorBtn.textContent = cameraSettings.mirror ? "🪞 Lật gương: BẬT" : "🪞 Lật gương: TẮT";
        mirrorBtn.classList.toggle("active-toggle", !!cameraSettings.mirror);
    }
    if (glareBtn) {
        glareBtn.textContent = cameraSettings.anti_glare ? "💡 Chống chói: BẬT" : "💡 Chống chói: TẮT";
        glareBtn.classList.toggle("active-toggle", !!cameraSettings.anti_glare);
    }
    if (denoiseBtn) {
        denoiseBtn.textContent = cameraSettings.denoise ? "🧹 Khử nhiễu: BẬT" : "🧹 Khử nhiễu: TẮT";
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

        // So sánh tránh render lại làm nhấp nháy UI
        if (logs.length === cachedLogs.length && JSON.stringify(logs) === JSON.stringify(cachedLogs)) {
            return;
        }
        cachedLogs = logs;

        // Cập nhật số lượng
        const countBadge = document.getElementById("log-count-badge");
        if (countBadge) countBadge.textContent = `${logs.length} sự kiện`;

        renderBehaviorTable(logs);
    } catch (e) {
        if (isServerOnline) {
            console.warn("Chưa lấy được nhật ký hành vi:", e.message || e);
        }
    }
}

function renderBehaviorTable(logs) {
    const tbody = document.getElementById("behavior-log-tbody");
    if (!tbody) return;

    if (!logs || logs.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="6" class="empty-cell">
                    <div class="empty-state-box">
                        <span class="empty-icon">🤖</span>
                        <p class="empty-title">Đang kết nối luồng phân tích hành vi Gemini AI chu kỳ 4s...</p>
                        <span class="empty-sub">Mỗi 4 giây, hệ thống tự động trích xuất khung hình gửi lên Gemini Vision để nhận diện hành vi và dự báo xu hướng động tác tiếp theo (13 RPM Free Quota).</span>
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
                    <span class="badge ${badgeClass}">${escapeHtml(item.action)}</span>
                </td>
                <td class="desc-cell">${escapeHtml(item.description)}</td>
                <td class="prediction-cell">
                    <div class="prediction-badge">
                        <span class="pred-icon">🔮</span>
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
        snapBtn.textContent = "📸 Đang chụp...";
    }
    try {
        const res = await fetch("/api/camera/snapshot", { method: "POST" });
        const data = await res.json();
        if (data.status === "success") {
            await fetchCameraLogs();
        } else {
            alert("Không thể chụp ảnh: " + (data.message || "Vui lòng bật camera"));
        }
    } catch (e) {
        alert("Lỗi khi gửi lệnh chụp snapshot: " + e);
    } finally {
        if (snapBtn) {
            snapBtn.disabled = false;
            snapBtn.textContent = "📸 Chụp Snapshot";
        }
    }
}

async function clearLogs() {
    if (!cachedLogs || cachedLogs.length === 0) {
        alert("Nhật ký hiện tại đang trống.");
        return;
    }
    if (!confirm("Bạn có chắc chắn muốn xóa toàn bộ danh sách nhật ký hành vi không?")) {
        return;
    }
    try {
        await fetch("/api/camera/logs/clear", { method: "POST" });
        cachedLogs = [];
        renderBehaviorTable([]);
        const countBadge = document.getElementById("log-count-badge");
        if (countBadge) countBadge.textContent = "0 sự kiện";
    } catch (e) {
        alert("Lỗi khi xóa nhật ký: " + e);
    }
}

function exportLogsToCSV() {
    if (!cachedLogs || cachedLogs.length === 0) {
        alert("Chưa có sự kiện nào trong nhật ký để xuất CSV.");
        return;
    }

    const headers = ["STT", "Mã sự kiện", "Thời gian", "Hành vi (4s qua)", "Mô tả chi tiết ngữ cảnh", "Dự đoán 4s tiếp theo", "Đường dẫn snapshot", "Mức độ an toàn"];
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

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        closeSnapshotModal();
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

    const dropzone = document.getElementById("video-dropzone");
    dropzone.innerHTML = `<div class="dropzone-content"><span class="spinner"></span><h4>Đang tải video lên hệ thống...</h4></div>`;

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
    dropzone.innerHTML = `
        <input type="file" id="video-file-input" accept="video/mp4,video/avi,video/quicktime,video/mkv" style="display:none" onchange="handleFileSelected(event)">
        <div class="dropzone-content">
            <span class="drop-icon">📤</span>
            <h4>Kéo thả video vào đây, hoặc <span class="highlight">nhấn để chọn file</span></h4>
            <p>Hỗ trợ định dạng .mp4, .avi, .mov, .mkv. Dung lượng tối đa 150MB.</p>
            <button type="button" class="btn btn-sm btn-outline" style="margin-top: 10px;" onclick="event.stopPropagation(); loadSampleVideo();">
                🎬 Sử dụng video mẫu (demo_synthetic.mp4)
            </button>
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
        alert("Vui lòng dán link video (YouTube / link trực tiếp).");
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
            alert("Không thể đọc video từ link: " + (probe.detail || JSON.stringify(probe)));
            return;
        }

        currentProbedURLData = probe;
        currentProbedURLData.url = url;

        // Nếu video ngắn (<= 180s = 3 phút): Tải trực tiếp toàn bộ
        if (!probe.is_long) {
            if (rangeBox) rangeBox.classList.add("hidden");
            btnText.textContent = "Đang tải video...";
            const res = await fetch("/api/video/import_url", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url })
            });
            const data = await res.json();
            if (data.status === "success") {
                loadVideoIntoTrimmer(data);
            } else {
                alert("Lỗi tải video từ URL: " + (data.detail || JSON.stringify(data)));
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
                        { label: "00:00 ➔ 01:30", s: 0, e: 90 }
                    ];
                    if (dur >= 300) candidates.push({ label: "05:00 ➔ 06:30", s: 300, e: 390 });
                    if (dur >= 600) candidates.push({ label: "10:00 ➔ 11:30", s: 600, e: 690 });
                    if (dur >= 900) candidates.push({ label: "15:00 ➔ 16:30", s: 900, e: 990 });
                    if (dur >= 1800) candidates.push({ label: "30:00 ➔ 31:30", s: 1800, e: 1890 });

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
        btnText.textContent = "🔍 Kiểm Tra & Nạp Video";
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

    spinner.classList.remove("hidden");
    btnText.textContent = `Đang trích xuất (${formatTime(startSec)} ➔ ${formatTime(endSec)})...`;
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
            alert("Lỗi trích xuất phân đoạn URL: " + (data.detail || JSON.stringify(data)));
        }
    } catch (e) {
        alert("Lỗi kết nối khi trích xuất phân đoạn URL: " + e);
    } finally {
        spinner.classList.add("hidden");
        btnText.textContent = "⚡ Tải Đúng Đoạn Này Vào CapCut";
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
    previewVid.src = videoData.stream_url;
    previewVid.load();

    previewVid.onloadedmetadata = () => {
        const dur = previewVid.duration || videoData.duration || 60;
        initSliders(dur);
    };

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
    const startVal = parseFloat(rangeStart.value);
    const endVal = parseFloat(rangeEnd.value);
    const selDuration = Math.max(0.1, endVal - startVal);

    document.getElementById("trim-start-display").textContent = formatTime(startVal);
    document.getElementById("trim-end-display").textContent = formatTime(endVal);
    document.getElementById("trim-duration-display").textContent = `(${selDuration.toFixed(1)} giây)`;

    // Token Guard Meter logic
    const meterBadge = document.getElementById("token-meter");
    const meterText = document.getElementById("token-meter-text");

    if (selDuration <= 60.0) {
        meterBadge.className = "token-meter-badge";
        meterBadge.innerHTML = `<span class="meter-icon">🟢</span><span>TỐI ƯU HOÀN HẢO (Xử lý ~15s, &lt;1,200 tokens)</span>`;
    } else if (selDuration <= 90.0) {
        meterBadge.className = "token-meter-badge warning";
        meterBadge.innerHTML = `<span class="meter-icon">🟡</span><span>ĐẠT TIÊU CHUẨN (Xử lý ~25s, ~1,500 tokens)</span>`;
    } else {
        meterBadge.className = "token-meter-badge danger";
        meterBadge.innerHTML = `<span class="meter-icon">🔴</span><span>VƯỢT QUÁ KHUYẾN NGHỊ (&gt;90s làm chậm GPU & tốn token)</span>`;
    }
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

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

    const payload = {
        video_path: currentVideoData.video_path,
        start_time: startVal,
        end_time: endVal,
        call_gemini: true
    };

    // Show processing section
    const procSec = document.getElementById("processing-section");
    procSec.classList.remove("hidden");
    document.getElementById("results-section").classList.add("hidden");
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
            const pct = job.progress_percent || 0;
            document.getElementById("proc-progress-fill").style.width = `${pct}%`;
            document.getElementById("proc-pct-text").textContent = `${pct}%`;
            document.getElementById("proc-frames-text").textContent = `Khung hình: ${job.current_frame} / ${job.total_frames}`;
            document.getElementById("proc-fps-badge").textContent = `${job.current_fps} FPS`;
        } else if (job.status === "completed") {
            clearInterval(jobPollInterval);
            document.getElementById("proc-progress-fill").style.width = `100%`;
            document.getElementById("proc-pct-text").textContent = `100%`;
            setTimeout(() => {
                document.getElementById("processing-section").classList.add("hidden");
                renderResults(job.result);
            }, 600);
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
    currentSegments = result.timeline_segments || [];
    currentHeatmapData = result.heatmap_data || [];
    allEntitiesDetected = result.entities_detected || [];
    activeFocusSegment = null;
    isLoopingSegment = false;
    activeEntityFilter = 'all';

    // Video Players
    const origVid = document.getElementById("result-orig-video");
    const annotVid = document.getElementById("result-annotated-video");
    origVid.src = currentVideoData.stream_url;
    annotVid.src = result.annotated_stream_url;

    // Download Button
    const dlBtn = document.getElementById("btn-download-mp4");
    if (dlBtn) dlBtn.href = result.download_url;

    // Gemini Synthesis Report
    const gemini = result.gemini_report || {};
    const threatBadge = document.getElementById("rep-threat-level");
    const threatLevel = gemini.threat_level || result.overall_danger_level || "AN TOÀN";

    if (threatLevel.includes("NGUY") || threatLevel.includes("DANGER")) {
        threatBadge.className = "badge badge-danger";
        threatBadge.textContent = "🔴 NGUY HIỂM";
    } else if (threatLevel.includes("CANH") || threatLevel.includes("WARNING")) {
        threatBadge.className = "badge badge-neutral";
        threatBadge.style.color = "var(--accent-amber)";
        threatBadge.textContent = "🟡 CẢNH BÁO";
    } else {
        threatBadge.className = "badge badge-safe";
        threatBadge.textContent = "● AN TOÀN";
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
    renderHeatmap(currentHeatmapData, result.duration_seconds || 10.0);

    // Render Entity Filters
    renderEntityFilters(allEntitiesDetected);

    // Render Timeline Segments Master Table
    renderTimelineSegments();
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
    };
}

function seekBothPlayers(seconds) {
    const origVid = document.getElementById("result-orig-video");
    const annotVid = document.getElementById("result-annotated-video");
    if (origVid) origVid.currentTime = seconds;
    if (annotVid) {
        annotVid.currentTime = seconds;
        annotVid.play().catch(() => {});
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
        cell.title = `[${slot.time_str}] Điểm đe dọa: ${slot.score} (${(slot.level || 'safe').toUpperCase()}) - Nhấn để tua`;
        cell.onclick = () => {
            seekBothPlayers(slot.time);
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
function renderEntityFilters(entities) {
    const container = document.getElementById("entity-filter-container");
    if (!container) return;

    container.innerHTML = `<span class="filter-label">Lọc đối tượng:</span>`;

    const allBtn = document.createElement("button");
    allBtn.className = `filter-chip ${activeEntityFilter === 'all' ? 'active' : ''}`;
    allBtn.id = "filter-chip-all";
    allBtn.textContent = `🔘 Tất cả (${entities.length || 0})`;
    allBtn.onclick = () => filterByEntity('all');
    container.appendChild(allBtn);

    entities.forEach(entId => {
        const chip = document.createElement("button");
        chip.className = `filter-chip ${activeEntityFilter === entId ? 'active' : ''}`;
        chip.innerHTML = `👤 ${escapeHtml(entId)}`;
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
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state" style="text-align:center; padding: 24px; color: var(--text-muted);">Không có phân đoạn hành vi nào được ghi nhận.</td></tr>`;
        return;
    }

    // Filter segments if activeEntityFilter !== 'all'
    const filtered = currentSegments.filter(seg => {
        if (activeEntityFilter === 'all') return true;
        return seg.entities && seg.entities.some(e => e.id === activeEntityFilter || (e.raw_id && activeEntityFilter.includes(e.raw_id)));
    });

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state" style="text-align:center; padding: 24px; color: var(--text-muted);">Không tìm thấy phân đoạn nào cho đối tượng <strong>${escapeHtml(activeEntityFilter)}</strong>.</td></tr>`;
        return;
    }

    let html = "";
    filtered.forEach((seg) => {
        const isFocused = activeFocusSegment && activeFocusSegment.segment_id === seg.segment_id;
        const rowClass = isFocused ? "active-segment-row" : "";
        const badgeClass = seg.severity === "danger" ? "badge badge-danger" : (seg.severity === "warning" ? "badge badge-neutral" : "badge badge-safe");
        const badgeText = seg.severity === "danger" ? "🔴 NGUY HIỂM" : (seg.severity === "warning" ? "🟡 CẢNH BÁO" : "● AN TOÀN");

        let entitiesHtml = "";
        if (seg.scene_summary) {
            entitiesHtml += `<div class="seg-scene-summary" style="margin-bottom: 8px; font-size: 0.90rem; font-weight: 500; color: var(--text-main); line-height: 1.45;">📝 ${escapeHtml(seg.scene_summary)}</div>`;
        }
        entitiesHtml += `<div class="seg-entities-list">`;
        (seg.entities || []).forEach(ent => {
            const entBadgeClass = ent.severity === "danger" ? "tag-danger" : (ent.severity === "warning" ? "tag-warning" : "tag-safe");
            entitiesHtml += `
                <div class="entity-item-row">
                    <span class="entity-tag ${entBadgeClass}">👤 ${escapeHtml(ent.id)}</span>
                    <strong class="entity-action-text">${escapeHtml(ent.action)}</strong>
                    <span class="entity-posture-text">(${escapeHtml(ent.posture)})</span>
                </div>
            `;
        });
        entitiesHtml += `</div>`;


        const summaryEscaped = escapeHtml(seg.scene_summary || "");
        const descEscaped = escapeHtml(seg.context_description || seg.scene_summary || "Phân đoạn ghi nhận đối tượng hoạt động");
        const predEscaped = escapeHtml(seg.prediction_next_4s || "Duy trì trạng thái tương tác an toàn trong các giây tiếp theo");
        const snapThumb = seg.snapshot_url 
            ? `<img src="${escapeHtml(seg.snapshot_url)}" class="seg-snapshot-thumb" 
                onclick="openSnapshotModal('${escapeHtml(seg.snapshot_url)}', '${escapeHtml(seg.segment_id)}', '${summaryEscaped}', '${escapeHtml(seg.time_range)}', '${descEscaped}', '${predEscaped}')"
                title="Bấm để phóng to ảnh chụp kèm Bounding Box" />`
            : `<span class="mono text-muted">--</span>`;

        html += `
            <tr class="${rowClass}" id="seg-row-${escapeHtml(seg.segment_id)}">
                <td>
                    <div class="seg-range-badge mono">${escapeHtml(seg.time_range)}</div>
                    <div class="seg-id-sub mono">${escapeHtml(seg.segment_id)}</div>
                </td>
                <td>
                    ${entitiesHtml}
                </td>
                <td>
                    <span class="${badgeClass}">${badgeText}</span>
                    <div class="threat-sub mono">Điểm: ${seg.danger_score || 0}</div>
                </td>
                <td style="text-align: center;">
                    ${snapThumb}
                </td>
                <td style="text-align: right;">
                    <button class="btn btn-sm btn-outline btn-focus-seg" 
                        onclick="focusTimelineSegment(${seg.start_sec}, ${seg.end_sec}, '${escapeHtml(seg.segment_id)}', '${summaryEscaped}')">
                        ▶️ Xem Đoạn Này
                    </button>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

// ==============================================================================
// SEGMENT FOCUS & PLAYBACK LOOP MECHANICS
// ==============================================================================
function focusTimelineSegment(startSec, endSec, segId, summary) {
    activeFocusSegment = {
        segment_id: segId,
        start_sec: parseFloat(startSec),
        end_sec: parseFloat(endSec),
        summary: summary
    };

    const banner = document.getElementById("segment-focus-banner");
    if (banner) {
        banner.classList.remove("hidden");
        safeSetText("focus-range-text", `${formatTime(startSec)} ➔ ${formatTime(endSec)}`);
        safeSetText("focus-summary-text", summary || "Đang xem lại phân đoạn");
    }

    seekBothPlayers(startSec);
    renderTimelineSegments();

    const playerSec = document.querySelector(".side-by-side-grid");
    if (playerSec) {
        playerSec.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function toggleLoopCurrentSegment() {
    isLoopingSegment = !isLoopingSegment;
    const btn = document.getElementById("btn-toggle-loop");
    if (btn) {
        btn.textContent = isLoopingSegment ? "🔁 Lặp đoạn này: BẬT" : "🔁 Lặp đoạn này: TẮT";
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
        btn.textContent = "🔁 Lặp đoạn này: TẮT";
        btn.className = "btn btn-xs btn-outline";
    }
    renderTimelineSegments();
}

// Chatbot Q&A
async function sendChatMessage() {
    const input = document.getElementById("chat-question-input");
    const question = input.value.trim();
    if (!question) return;

    const ansBox = document.getElementById("chat-answer-box");
    const ansText = document.getElementById("chat-answer-text");
    ansBox.classList.remove("hidden");
    ansText.innerHTML = `<span class="spinner"></span> Đang truy vấn Gemini 3.5 Flash Lite...`;

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, job_id: currentJobId })
        });
        const data = await res.json();
        ansText.textContent = data.answer || "Không nhận được phản hồi từ AI.";
    } catch (e) {
        ansText.textContent = "Lỗi kết nối khi hỏi đáp: " + e;
    }
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

