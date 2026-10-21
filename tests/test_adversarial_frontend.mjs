// Adversarial Frontend Stress Testing Suite for ui/static/app.js
// Tests Requirement R1 (Event Flow Streams), Requirement R3 (Timeline & Grounding), Deduplication, Edge Cases
import fs from 'fs';
import path from 'path';
import vm from 'vm';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const appJsPath = path.resolve(__dirname, '../ui/static/app.js');

class MockElement {
    constructor(id = '', tag = 'div') {
        this.id = id;
        this.tagName = tag.toUpperCase();
        this._innerHTML = '';
        this.textContent = '';
        this.classList = {
            _classes: new Set(),
            add: (...classes) => classes.forEach(c => this.classList._classes.add(c)),
            remove: (...classes) => classes.forEach(c => this.classList._classes.delete(c)),
            contains: (c) => this.classList._classes.has(c),
            toggle: (c) => {
                if (this.classList._classes.has(c)) {
                    this.classList._classes.delete(c);
                    return false;
                } else {
                    this.classList._classes.add(c);
                    return true;
                }
            }
        };
        this.style = {};
        this.children = [];
    }
    get innerHTML() {
        if (this.children && this.children.length > 0) {
            return this._innerHTML + this.children.map(c => `<${c.tagName.toLowerCase()} class="${Array.from(c.classList._classes).join(' ')}">${c.innerHTML}</${c.tagName.toLowerCase()}>`).join('');
        }
        return this._innerHTML;
    }
    set innerHTML(val) {
        this._innerHTML = String(val);
        this.children = [];
    }
    getBoundingClientRect() {
        return { left: 100, top: 200, width: 200, height: 60, right: 300, bottom: 260 };
    }
    setAttribute(k, v) { this[k] = v; }
    getAttribute(k) { return this[k] || null; }
    appendChild(el) { this.children.push(el); }
    removeChild(el) {
        const idx = this.children.indexOf(el);
        if (idx !== -1) this.children.splice(idx, 1);
    }
}

function createDOMContext() {
    const elements = new Map();
    const getOrCreate = (id, tag = 'div') => {
        if (!elements.has(id)) {
            elements.set(id, new MockElement(id, tag));
        }
        return elements.get(id);
    };

    const documentMock = {
        getElementById: (id) => getOrCreate(id),
        createElement: (tag) => new MockElement('', tag),
        querySelectorAll: () => [],
        querySelector: () => null,
        addEventListener: () => {},
        documentElement: new MockElement('html', 'html'),
        body: new MockElement('body', 'body')
    };

    const windowMock = {
        document: documentMock,
        localStorage: {
            getItem: () => null,
            setItem: () => {}
        },
        addEventListener: () => {},
        setInterval: () => 999,
        clearInterval: () => {},
        setTimeout: (cb) => { cb(); return 1; },
        clearTimeout: () => {},
        location: { hostname: 'localhost', port: '8080' },
        navigator: { userAgent: 'AdversarialTestHarness/1.0' },
        fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    };
    windowMock.window = windowMock;

    const sandbox = {
        window: windowMock,
        document: documentMock,
        localStorage: windowMock.localStorage,
        console: {
            log: () => {},
            error: () => {},
            warn: () => {},
            info: () => {}
        },
        setInterval: windowMock.setInterval,
        clearInterval: windowMock.clearInterval,
        setTimeout: windowMock.setTimeout,
        clearTimeout: windowMock.clearTimeout,
        Math: Math,
        parseFloat: parseFloat,
        parseInt: parseInt,
        String: String,
        Number: Number,
        Boolean: Boolean,
        Array: Array,
        Object: Object,
        RegExp: RegExp,
        Date: Date,
        Map: Map,
        Set: Set
    };

    const context = vm.createContext(sandbox);
    const code = fs.readFileSync(appJsPath, 'utf8');
    vm.runInContext(code, context);

    // In a browser, all top-level functions in a <script> become properties of window
    for (const key of Object.keys(context)) {
        if (typeof context[key] === 'function' && !windowMock[key]) {
            windowMock[key] = context[key];
        }
    }

    return { context, sandbox, elements, getOrCreate };
}

// Test Runner Framework
let totalPassed = 0;
let totalFailed = 0;
const testResults = [];

function assert(condition, message) {
    if (!condition) {
        throw new Error(message || "Assertion failed");
    }
}

function test(name, fn) {
    try {
        fn();
        totalPassed++;
        testResults.push({ name, status: "PASS" });
        console.log(`  [PASS] ${name}`);
    } catch (err) {
        totalFailed++;
        testResults.push({ name, status: "FAIL", error: err.message, stack: err.stack });
        console.error(`  [FAIL] ${name}: ${err.message}`);
    }
}

console.log("================================================================================");
console.log("  STARTING ADVERSARIAL FRONTEND STRESS TEST SUITE (ui/static/app.js)");
console.log("================================================================================");

// ==============================================================================
// TEST GROUP 1: EMPTY STATE HANDLING
// ==============================================================================
console.log("\n>> Test Group 1: Empty timeline_segments Handling");

test("TC-01: drawEventCentricFlowStreams with empty array produces elegant empty state", () => {
    const env = createDOMContext();
    const container = env.getOrCreate("multi-track-actor-timeline");
    env.sandbox.window.drawEventCentricFlowStreams([], 30.0);
    assert(container.innerHTML.includes("empty-state-box"), "Container must contain empty-state-box");
    assert(container.innerHTML.includes("Chưa có dữ liệu dòng diễn biến sự kiện"), "Container must show friendly Vietnamese empty title");
    assert(!container.innerHTML.includes("undefined"), "Must not contain undefined");
    assert(!container.innerHTML.includes("null"), "Must not contain null");
});

test("TC-02: drawEventCentricFlowStreams with null/undefined segments falls back to empty state", () => {
    const env = createDOMContext();
    const container = env.getOrCreate("multi-track-actor-timeline");
    env.sandbox.currentSegments = [];
    env.sandbox.window.drawEventCentricFlowStreams(null, 30.0);
    assert(container.innerHTML.includes("Chưa có dữ liệu dòng diễn biến sự kiện"), "Must handle null segments gracefully");

    env.sandbox.window.drawEventCentricFlowStreams(undefined, 30.0);
    assert(container.innerHTML.includes("Chưa có dữ liệu dòng diễn biến sự kiện"), "Must handle undefined segments gracefully");
});

test("TC-03: drawEventCentricFlowStreams with zero/negative/NaN duration does not throw or NaN-out", () => {
    const env = createDOMContext();
    const container = env.getOrCreate("multi-track-actor-timeline");
    // Should clamp duration to Math.max(1.0, ...)
    env.sandbox.window.drawEventCentricFlowStreams([], 0);
    assert(container.innerHTML.includes("empty-state-box"));

    env.sandbox.window.drawEventCentricFlowStreams([], -50);
    assert(container.innerHTML.includes("empty-state-box"));

    env.sandbox.window.drawEventCentricFlowStreams([], NaN);
    assert(container.innerHTML.includes("empty-state-box"));
});

test("TC-04: renderTimelineSegments with empty currentSegments renders empty table row", () => {
    const env = createDOMContext();
    const tbody = env.getOrCreate("timeline-segments-tbody");
    vm.runInContext("currentSegments = [];", env.context);
    env.sandbox.window.renderTimelineSegments();
    assert(tbody.innerHTML.includes("empty-row"), "Table body must contain empty-row class");
    assert(tbody.innerHTML.includes("Chưa có phân đoạn hành vi dòng thời gian"), "Must render polite empty message");
    assert(!tbody.innerHTML.includes("undefined"), "Must not contain undefined");
});

test("TC-05: renderTimelineSegments with non-matching filter renders empty filter state", () => {
    const env = createDOMContext();
    const tbody = env.getOrCreate("timeline-segments-tbody");
    vm.runInContext(`
        currentSegments = [
            { segment_id: "SEG-01", start_sec: 0, end_sec: 4, severity: "safe", entities: [{ id: "ID #01", action: "Đọc sách" }] }
        ];
        activeEntityFilter = 'ID #99';
    `, env.context);
    env.sandbox.window.renderTimelineSegments();
    assert(tbody.innerHTML.includes("Không tìm thấy phân đoạn phù hợp"), "Must show filter-empty state");
    assert(tbody.innerHTML.includes("ID #99"), "Must mention filter query");
});

// ==============================================================================
// TEST GROUP 2: EXTREME SCALE & LONG VIDEO (100+ SEGMENTS, 3600S)
// ==============================================================================
console.log("\n>> Test Group 2: Extreme Scale (120 Segments, 3600s Video)");

test("TC-06: drawEventCentricFlowStreams with 120 segments executes quickly and produces correct elements", () => {
    const env = createDOMContext();
    const container = env.getOrCreate("multi-track-actor-timeline");

    // Generate 120 segments
    const segments = [];
    for (let i = 0; i < 120; i++) {
        const start = i * 30;
        const end = (i + 1) * 30;
        const sev = i % 10 === 0 ? "danger" : (i % 3 === 0 ? "warning" : "safe");
        segments.push({
            segment_id: `SEG-${String(i + 1).padStart(3, '0')}`,
            start_sec: start,
            end_sec: end,
            severity: sev,
            danger_score: sev === "danger" ? 8.5 : (sev === "warning" ? 5.2 : 1.1),
            event_milestone: `Mốc sự kiện phân đoạn ${i + 1}`,
            telemetry_breakdown: {
                max_velocity: 120 + i,
                min_distance: 45 + (i % 50),
                dominant_posture: "Đứng đối diện"
            },
            entities: [
                { id: `ID #01`, role: "Khiêu khích", action: "Tiến lại gần", severity: sev },
                { id: `ID #02`, role: "Phòng thủ", action: "Lùi lại", severity: sev }
            ]
        });
    }

    const t0 = Date.now();
    env.sandbox.window.drawEventCentricFlowStreams(segments, 3600);
    const elapsed = Date.now() - t0;

    assert(elapsed < 100, `Execution should take < 100ms, took ${elapsed}ms`);
    assert(container.innerHTML.includes("Mạch Diễn Biến Tương Tác"), "Must contain Interaction Stream header");
    assert(container.innerHTML.includes("Mạch Cảnh Báo An Ninh"), "Must contain Threat Risk Stream header");

    // Check count of narrative pills
    const narrativePillMatches = container.innerHTML.match(/event-narrative-pill/g);
    assert(narrativePillMatches && narrativePillMatches.length === 120, `Expected 120 narrative pills, got ${narrativePillMatches ? narrativePillMatches.length : 0}`);

    // Check count of threat risk pills
    const threatPillMatches = container.innerHTML.match(/threat-risk-pill/g);
    assert(threatPillMatches && threatPillMatches.length === 120, `Expected 120 threat pills, got ${threatPillMatches ? threatPillMatches.length : 0}`);

    // Check connecting arrows: (120 - 1) * 2 = 238 arrows
    const arrowMatches = container.innerHTML.match(/stream-flow-arrow/g);
    assert(arrowMatches && arrowMatches.length === 238, `Expected 238 connecting arrows, got ${arrowMatches ? arrowMatches.length : 0}`);

    // Verify first and last segment IDs present in pills
    assert(container.innerHTML.includes('id="event-pill-SEG-001"'), "Must contain first event pill ID");
    assert(container.innerHTML.includes('id="event-pill-SEG-120"'), "Must contain last event pill ID");
    assert(container.innerHTML.includes('id="risk-pill-SEG-001"'), "Must contain first risk pill ID");
    assert(container.innerHTML.includes('id="risk-pill-SEG-120"'), "Must contain last risk pill ID");
    assert(container.innerHTML.includes("Tổng thời lượng: <strong>60:00</strong> (120 phân đoạn sự kiện)"), "Must correctly format total 60:00 duration and 120 segments");
});

test("TC-07: renderTimelineSegments with 120 segments renders all rows without bottleneck", () => {
    const env = createDOMContext();
    const tbody = env.getOrCreate("timeline-segments-tbody");

    const segments = [];
    for (let i = 0; i < 120; i++) {
        segments.push({
            segment_id: `SEG-${String(i + 1).padStart(3, '0')}`,
            time_range: `${i * 30}s - ${(i + 1) * 30}s`,
            start_sec: i * 30,
            end_sec: (i + 1) * 30,
            severity: i % 5 === 0 ? "danger" : "safe",
            danger_score: 3.5,
            scene_summary: `Tóm tắt phân đoạn ${i + 1}`,
            entities: [{ id: "ID #01", action: "Hoạt động" }]
        });
    }

    vm.runInContext(`currentSegments = ${JSON.stringify(segments)}; activeEntityFilter = 'all';`, env.context);
    const t0 = Date.now();
    env.sandbox.window.renderTimelineSegments();
    const elapsed = Date.now() - t0;

    assert(elapsed < 100, `Table render must take < 100ms, took ${elapsed}ms`);
    const rowMatches = tbody.innerHTML.match(/<tr class="" id="seg-row-SEG-/g);
    assert(rowMatches && rowMatches.length === 120, `Expected 120 rows, got ${rowMatches ? rowMatches.length : 0}`);
});

test("TC-08: updateEventFlowPlayhead accurately toggles active-pill at extreme timestamps", () => {
    const env = createDOMContext();
    const segs = [
        { segment_id: "SEG-01", start_sec: 0, end_sec: 10 },
        { segment_id: "SEG-02", start_sec: 10, end_sec: 25 },
        { segment_id: "SEG-03", start_sec: 25, end_sec: 60 }
    ];
    vm.runInContext(`currentSegments = ${JSON.stringify(segs)};`, env.context);

    const p1E = env.getOrCreate("event-pill-SEG-01");
    const p1R = env.getOrCreate("risk-pill-SEG-01");
    const p2E = env.getOrCreate("event-pill-SEG-02");
    const p2R = env.getOrCreate("risk-pill-SEG-02");
    const p3E = env.getOrCreate("event-pill-SEG-03");
    const p3R = env.getOrCreate("risk-pill-SEG-03");

    // Playhead at t=5s (SEG-01 active)
    env.sandbox.window.updateEventFlowPlayhead(5);
    assert(p1E.classList.contains("active-pill"), "SEG-01 event pill must be active at 5s");
    assert(p1R.classList.contains("active-pill"), "SEG-01 risk pill must be active at 5s");
    assert(!p2E.classList.contains("active-pill"), "SEG-02 event pill must not be active at 5s");

    // Playhead at t=15s (SEG-02 active, SEG-01 deactivated)
    env.sandbox.window.updateEventFlowPlayhead(15);
    assert(!p1E.classList.contains("active-pill"), "SEG-01 must be deactivated at 15s");
    assert(p2E.classList.contains("active-pill"), "SEG-02 must be active at 15s");
    assert(p2R.classList.contains("active-pill"), "SEG-02 risk pill must be active at 15s");

    // Playhead out of bounds at t=100s (all deactivated)
    env.sandbox.window.updateEventFlowPlayhead(100);
    assert(!p1E.classList.contains("active-pill"));
    assert(!p2E.classList.contains("active-pill"));
    assert(!p3E.classList.contains("active-pill"));
});

// ==============================================================================
// TEST GROUP 3: MALFORMED / NOISY ENTITY STRINGS & 100% DEDUPLICATION
// ==============================================================================
console.log("\n>> Test Group 3: Malformed / Noisy Entity Strings & Deduplication Filter");

test("TC-09: Deduplication of 'Đối tượng #05 (ID #05)' cleans ID to 'ID #05'", () => {
    const env = createDOMContext();
    const tbody = env.getOrCreate("timeline-segments-tbody");
    const segs = [{
        segment_id: "SEG-01",
        time_range: "00:00 - 00:04",
        start_sec: 0,
        end_sec: 4,
        severity: "safe",
        entities: [
            { id: "Đối tượng #05 (ID #05)", role: "Đối tượng #05", distinctive_anchor: "Đối tượng #05", action: "Đang ngồi" }
        ]
    }];
    vm.runInContext(`currentSegments = ${JSON.stringify(segs)}; activeEntityFilter = 'all';`, env.context);
    env.sandbox.window.renderTimelineSegments();

    assert(tbody.innerHTML.includes("ID #05"), "Must contain clean 'ID #05'");
    // Verify that 'Đối tượng #05' is NOT rendered anywhere in entity tags, badges, or anchors
    assert(!tbody.innerHTML.includes("Đối tượng #05 (ID #05)"), "Must not contain raw uncleaned ID string");
    assert(!tbody.innerHTML.includes("entity-role-badge"), "Generic role 'Đối tượng #05' must be eliminated");
    assert(!tbody.innerHTML.includes("entity-anchor-badge"), "Generic anchor 'Đối tượng #05' must be eliminated");
});

test("TC-10: Deduplication of 'Học sinh áo trắng (ID #02)' with role 'Học sinh áo trắng' suppresses duplicate role badge", () => {
    const env = createDOMContext();
    const tbody = env.getOrCreate("timeline-segments-tbody");
    const segs = [{
        segment_id: "SEG-01",
        time_range: "00:00 - 00:04",
        start_sec: 0,
        end_sec: 4,
        severity: "warning",
        entities: [
            {
                id: "Học sinh áo trắng (ID #02)",
                role: "Học sinh áo trắng",
                distinctive_anchor: "Học sinh áo trắng",
                action: "Quan sát"
            }
        ]
    }];
    vm.runInContext(`currentSegments = ${JSON.stringify(segs)}; activeEntityFilter = 'all';`, env.context);
    env.sandbox.window.renderTimelineSegments();

    // The clean ID and name are rendered concisely
    assert(tbody.innerHTML.includes("ID #02"), "Entity ID tag must display");
    assert(tbody.innerHTML.includes("Học sinh áo trắng"), "Entity name must display");
    // Duplicate role/anchor badges should NOT be rendered in the table
    assert(!tbody.innerHTML.includes("entity-role-badge"), "Duplicate role badge 'Học sinh áo trắng' must be suppressed");
    assert(!tbody.innerHTML.includes("entity-anchor-badge"), "Duplicate anchor badge 'Học sinh áo trắng' must be suppressed");
});

test("TC-11: Deduplication of '(Chủ thể chính)' tag and duplicate role text", () => {
    const env = createDOMContext();
    const tbody = env.getOrCreate("timeline-segments-tbody");
    const segs = [{
        segment_id: "SEG-01",
        time_range: "00:00 - 00:04",
        start_sec: 0,
        end_sec: 4,
        severity: "safe",
        entities: [
            { id: "Đối tượng #03 (Chủ thể chính)", role: "Chủ thể #03", distinctive_anchor: "Khu vực #03", action: "Giao tiếp" }
        ]
    }];
    vm.runInContext(`currentSegments = ${JSON.stringify(segs)}; activeEntityFilter = 'all';`, env.context);
    env.sandbox.window.renderTimelineSegments();

    assert(!tbody.innerHTML.includes("(Chủ thể chính)"), "(Chủ thể chính) suffix must be stripped");
    assert(!tbody.innerHTML.includes("entity-role-badge"), "Generic role 'Chủ thể #03' must be eliminated");
    assert(!tbody.innerHTML.includes("entity-anchor-badge"), "Generic anchor 'Khu vực #03' must be eliminated");
});

test("TC-12: Legit distinctive anchor and causal role preserved when non-duplicate", () => {
    const env = createDOMContext();
    const tbody = env.getOrCreate("timeline-segments-tbody");
    const segs = [{
        segment_id: "SEG-01",
        time_range: "00:00 - 00:04",
        start_sec: 0,
        end_sec: 4,
        severity: "danger",
        entities: [
            {
                id: "ID #01",
                role: "Khiêu khích tấn công",
                distinctive_anchor: "Bên trái bục giảng",
                action: "Lao tới đấm",
                posture: "Cúi gập người",
                severity: "danger"
            }
        ]
    }];
    vm.runInContext(`currentSegments = ${JSON.stringify(segs)}; activeEntityFilter = 'all';`, env.context);
    env.sandbox.window.renderTimelineSegments();

    assert(tbody.innerHTML.includes("ID #01"), "Clean ID tag must render");
    assert(tbody.innerHTML.includes("Khiêu khích tấn công"), "Role text must render on chip");
    assert(tbody.innerHTML.includes("tag-danger"), "Danger entity must have tag-danger class");

    // Action text is rendered in the detailed entity cards modal
    env.sandbox.window.openSegmentDetailModal("SEG-01");
    const modalCards = env.getOrCreate("seg-modal-entity-matrix");
    assert(modalCards.innerHTML.includes("Lao tới đấm"), "Detailed action text must render in modal card");
});

test("TC-13: Robust handling of missing entity fields (null, undefined, missing keys)", () => {
    const env = createDOMContext();
    const tbody = env.getOrCreate("timeline-segments-tbody");
    const segs = [{
        segment_id: "SEG-01",
        time_range: "00:00 - 00:04",
        start_sec: 0,
        end_sec: 4,
        entities: [
            { id: null, role: null, distinctive_anchor: null, action: null, posture: null },
            {} // completely empty entity object
        ]
    }];
    vm.runInContext(`currentSegments = ${JSON.stringify(segs)}; activeEntityFilter = 'all';`, env.context);
    // Must execute without throwing
    env.sandbox.window.renderTimelineSegments();
    assert(tbody.innerHTML.includes("ID #01") || tbody.innerHTML.includes("Chủ thể"), "Default fallback entity ID must render");
});

// ==============================================================================
// TEST GROUP 4: MILESTONE TITLE INFERENCE WITH MISSING OPTIONAL FIELDS
// ==============================================================================
console.log("\n>> Test Group 4: Milestone Title Inference (getSegmentMilestoneTitle)");

test("TC-14: Milestone inference with explicit event_milestone returns trimmed milestone", () => {
    const env = createDOMContext();
    const fn = env.sandbox.window.getSegmentMilestoneTitle;
    assert(fn({ event_milestone: "  Can ngăn / Vãn hồi  " }) === "Can ngăn / Vãn hồi");
    assert(fn({ event_milestone: "Xô xát thể xác" }) === "Xô xát thể xác");
});

test("TC-15: Milestone inference with missing event_milestone falls back to detailed_action", () => {
    const env = createDOMContext();
    const fn = env.sandbox.window.getSegmentMilestoneTitle;
    assert(fn({ detailed_action: "Tiếp cận đối đầu căng thẳng" }) === "Tiếp cận đối đầu căng thẳng");
    // If detailed_action > 40 chars, it should fall back to semantic inference
    const longAction = "Hành động này dài quá bốn mươi ký tự nên không được chọn làm tiêu đề pill ngắn";
    const res = fn({ detailed_action: longAction, severity: "danger" });
    assert(res === "Xô xát thể xác", `Long detailed_action must fall back to severity inference, got: ${res}`);
});

test("TC-16: Milestone inference falls back to short macro_narrative without periods", () => {
    const env = createDOMContext();
    const fn = env.sandbox.window.getSegmentMilestoneTitle;
    assert(fn({ macro_narrative: "Tự học và thảo luận" }) === "Tự học và thảo luận");
    // If macro_narrative contains a period, it is a sentence, not a title pill -> falls back
    const res = fn({ macro_narrative: "Hai bên nói chuyện.", severity: "warning" });
    assert(res === "Tiếp cận đối đầu", `Sentence with dot must fall back, got: ${res}`);
});

test("TC-17: Semantic keyword inference across scene_summary, context_description, actions", () => {
    const env = createDOMContext();
    const fn = env.sandbox.window.getSegmentMilestoneTitle;

    // Can ngăn / Vãn hồi keywords
    assert(fn({ scene_summary: "Có bảo vệ xuất hiện can ngăn hai bên" }) === "Can ngăn / Vãn hồi");
    assert(fn({ context_description: "Thầy giáo can thiệp hạ nhiệt căng thẳng" }) === "Can ngăn / Vãn hồi");
    assert(fn({ entities: [{ action: "vãn hồi trật tự", role: "người can" }] }) === "Can ngăn / Vãn hồi");

    // Xô xát thể xác keywords
    assert(fn({ scene_summary: "Hai đối tượng lao vào đấm túi bụi" }) === "Xô xát thể xác");
    assert(fn({ context_description: "Xuất hiện xung đột thể xác tại góc phòng" }) === "Xô xát thể xác");
    assert(fn({ severity: "danger" }) === "Xô xát thể xác");

    // Tiếp cận đối đầu keywords
    assert(fn({ scene_summary: "Đối tượng áp sát gây hấn đối phương" }) === "Tiếp cận đối đầu");
    assert(fn({ context_description: "Đứng thủ thế và tranh cãi to tiếng" }) === "Tiếp cận đối đầu");
    assert(fn({ severity: "warning" }) === "Tiếp cận đối đầu");

    // Normal baseline (eliminated 'Bình thường / Tự học' to avoid AI slop/bias)
    assert(fn({ scene_summary: "Học sinh đang ngồi đọc tài liệu" }) === "Vận động tự nhiên" || fn({ scene_summary: "Học sinh đang ngồi đọc tài liệu" }).includes("tài liệu"));
});

test("TC-18A: Milestone title inference with all combinations of missing optional fields", () => {
    const env = createDOMContext();
    const fn = env.sandbox.window.getSegmentMilestoneTitle;

    // All optional fields omitted / undefined / null (fallback is 'Vận động tự nhiên')
    assert(fn(null) === "Vận động tự nhiên", "null segment");
    assert(fn(undefined) === "Vận động tự nhiên", "undefined segment");
    assert(fn({}) === "Vận động tự nhiên", "empty segment object");
    assert(fn({ event_milestone: null, detailed_action: null, macro_narrative: null, entities: null }) === "Vận động tự nhiên", "all optional fields null");
    assert(fn({ event_milestone: "", detailed_action: "", macro_narrative: "", entities: [] }) === "Vận động tự nhiên", "all optional fields empty string/array");
    
    // Partial omissions
    assert(fn({ event_milestone: null, detailed_action: "Hành động cụ thể" }) === "Hành động cụ thể", "missing milestone, present detailed_action");
    assert(fn({ event_milestone: "", detailed_action: "", macro_narrative: "Quan sát chung" }) === "Quan sát chung", "missing milestone/action, present macro_narrative");
    assert(fn({ event_milestone: null, scene_summary: "Đang can ngăn" }) === "Can ngăn / Vãn hồi", "missing titles, inferred can ngan");
    assert(fn({ event_milestone: null, severity: "danger" }) === "Xô xát thể xác", "missing titles, inferred danger");
    assert(fn({ event_milestone: null, severity: "warning" }) === "Tiếp cận đối đầu", "missing titles, inferred warning");
});

test("TC-18B: Adversarial type resilience on seg.entities (non-array / null-element entity trap)", () => {
    const env = createDOMContext();
    const fn = env.sandbox.window.getSegmentMilestoneTitle;

    // In adversarial or malformed API responses where entities is a non-array truthy or contains null:
    // It should be safely absorbed without throwing TypeError
    let threwNonArray = false;
    try {
        fn({ entities: "not an array" });
    } catch (e) {
        threwNonArray = true;
    }

    let threwNullElem = false;
    try {
        fn({ entities: [null] });
    } catch (e) {
        threwNullElem = true;
    }

    assert(threwNonArray === false && threwNullElem === false, "Must gracefully absorb non-array / null-element entity trap without throwing");
});

// ==============================================================================
// TEST GROUP 5: TOOLTIP & HOVER INTEGRATION
// ==============================================================================
console.log("\n>> Test Group 5: Tooltip & Direct Seek Click Handlers");

test("TC-19: showEventFlowTooltip generates rich HTML and positions safely", () => {
    const env = createDOMContext();
    const tooltip = env.getOrCreate("event-flow-tooltip");
    const container = env.getOrCreate("actor-tracks-box");

    const segs = [{
        segment_id: "SEG-01",
        start_sec: 0,
        end_sec: 4,
        severity: "danger",
        danger_score: 9.2,
        scene_summary: "Xung đột kịch liệt tại cửa lớp",
        entities: [
            { id: "Đối tượng #01 (ID #01)", action: "Lao vào tấn công" }
        ]
    }];
    vm.runInContext(`currentSegments = ${JSON.stringify(segs)};`, env.context);

    const mockEvent = {
        currentTarget: {
            getBoundingClientRect: () => ({ left: 200, top: 300, width: 150, height: 40 })
        }
    };

    env.sandbox.window.showEventFlowTooltip(mockEvent, 0);

    assert(!tooltip.classList.contains("hidden"), "Tooltip must not be hidden");
    assert(tooltip.innerHTML.includes("SEG-01"), "Tooltip must contain segment ID");
    assert(tooltip.innerHTML.includes("Mốc sự kiện: Xô xát thể xác"), "Tooltip must contain inferred milestone");
    assert(tooltip.innerHTML.includes("9.2/10"), "Tooltip must contain danger score");
    assert(tooltip.innerHTML.includes("Xung đột kịch liệt tại cửa lớp"), "Tooltip must contain scene summary");
    assert(tooltip.innerHTML.includes("Lao vào tấn công"), "Tooltip must list actor action");
    assert(tooltip.innerHTML.includes("ID #01"), "Actor ID in tooltip must be cleaned");
    assert(tooltip.style.left !== undefined, "Left position must be set");
    assert(tooltip.style.top !== undefined, "Top position must be set");

    // Test hideEventFlowTooltip
    env.sandbox.window.hideEventFlowTooltip();
    assert(tooltip.classList.contains("hidden"), "Tooltip must be hidden after hideEventFlowTooltip()");
});

test("TC-20: Direct Seek onclick handlers are correctly wired in generated HTML", () => {
    const env = createDOMContext();
    const container = env.getOrCreate("multi-track-actor-timeline");

    const segs = [{
        segment_id: "SEG-01",
        start_sec: 12.5,
        end_sec: 16.5,
        severity: "warning",
        danger_score: 4.5,
        telemetry_breakdown: { max_velocity: 80, min_distance: 60 }
    }];

    env.sandbox.window.drawEventCentricFlowStreams(segs, 30.0);

    // Verify seekBothPlayers is called with exact second 12.5 in narrative pill
    assert(container.innerHTML.includes("onclick=\"seekBothPlayers(12.5, false, this, 'Mốc [00:12 - 00:16]')\""), "Narrative pill must have seekBothPlayers onclick");
    // Verify seekBothPlayers is called with exact second 12.5 in risk pill
    assert(container.innerHTML.includes("onclick=\"seekBothPlayers(12.5, false, this, 'Mốc [00:12 - 00:16]')\""), "Threat risk pill must have seekBothPlayers onclick");
});

test("TC-21: XSS Injection Resistance across Pills and Timeline Rows", () => {
    const env = createDOMContext();
    const container = env.getOrCreate("multi-track-actor-timeline");
    const tbody = env.getOrCreate("timeline-segments-tbody");

    const maliciousSegs = [{
        segment_id: 'SEG-<script>alert("seg")</script>',
        start_sec: 0,
        end_sec: 5,
        severity: "danger",
        danger_score: 9.9,
        event_milestone: '<img src=x onerror=alert("milestone")>',
        scene_summary: '<b onmouseover="alert(\'summary\')">Hack</b>',
        telemetry_breakdown: {
            max_velocity: '"><script>alert(1)</script>',
            min_distance: '<svg onload=alert(2)>'
        },
        entities: [
            {
                id: '<script>alert("ent")</script>',
                role: '<span onclick="alert(3)">Role</span>',
                distinctive_anchor: '<div style="background:red">Anchor</div>',
                action: '<img src=y>'
            }
        ]
    }];

    // 1. Test Event Centric Flow Streams
    env.sandbox.window.drawEventCentricFlowStreams(maliciousSegs, 30.0);
    assert(!container.innerHTML.includes("<script>"), "Raw <script> tags must not exist in stream pills HTML");
    assert(!container.innerHTML.includes("<img src=x onerror"), "Raw <img> payload must not exist in stream pills HTML");
    assert(container.innerHTML.includes("&lt;script&gt;"), "Must be escaped to &lt;script&gt;");

    // 2. Test Timeline Segments
    vm.runInContext(`currentSegments = ${JSON.stringify(maliciousSegs)}; activeEntityFilter = 'all';`, env.context);
    env.sandbox.window.renderTimelineSegments();
    assert(!tbody.innerHTML.includes("<script>"), "Raw <script> tags must not exist in timeline table HTML");
    assert(!tbody.innerHTML.includes("<span onclick"), "Role onclick attribute must be escaped in table");
    assert(tbody.innerHTML.includes("&lt;span onclick="), "Role injection must be escaped");

    // 3. Test Detail Modal Cards
    env.sandbox.window.openSegmentDetailModal('SEG-<script>alert("seg")</script>');
    const modalCards = env.getOrCreate("seg-modal-entity-matrix");
    assert(!modalCards.innerHTML.includes("<img src=y>"), "Raw entity action tags must not exist unescaped in modal");
    assert(modalCards.innerHTML.includes("&lt;img src=y&gt;"), "Entity action tag must be escaped in modal");
});

// ==============================================================================
// TEST SUMMARY & VERDICT
// ==============================================================================
console.log("\n================================================================================");
console.log("  ADVERSARIAL FRONTEND STRESS TEST RESULTS");
console.log("================================================================================");
console.log(`  Total Tests Run:  ${totalPassed + totalFailed}`);
console.log(`  Passed Tests:    ${totalPassed}`);
console.log(`  Failed Tests:    ${totalFailed}`);
console.log(`  Success Rate:    ${((totalPassed / (totalPassed + totalFailed)) * 100).toFixed(1)}%`);
console.log("================================================================================");

if (totalFailed > 0) {
    console.error("OVERALL VERDICT: FAIL - Regressions detected in frontend logic.");
    process.exit(1);
} else {
    console.log("OVERALL VERDICT: PASS - All adversarial stress checks passed 100%.");
    process.exit(0);
}
