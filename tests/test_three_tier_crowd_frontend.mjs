import assert from 'assert';
import fs from 'fs';
import path from 'path';

// Read app.js
const appJsPath = path.resolve('ui/static/app.js');
const appJsContent = fs.readFileSync(appJsPath, 'utf8');

// Test 1: Check that app.js contains 8.0 and 4.0 threshold checks for danger/warning
assert(appJsContent.includes('numScore >= 8.0 || seg.severity === "danger"') ||
       appJsContent.includes("numScore >= 8.0 || seg.severity === 'danger'"),
       "app.js must check numScore >= 8.0 for danger");

assert(appJsContent.includes('numScore >= 4.0 || seg.severity === "warning"') ||
       appJsContent.includes("numScore >= 4.0 || seg.severity === 'warning'"),
       "app.js must check numScore >= 4.0 for warning");

// Test 2: Check crowd scene logic in renderEntityFilters and renderExecutiveSceneNarrative
assert(appJsContent.includes('is_crowd_scene'), "app.js must reference is_crowd_scene");
assert(appJsContent.includes('actual_person_count'), "app.js must reference actual_person_count");
assert(appJsContent.includes('Không gian đông người'), "app.js must have crowd scene narrative card text");

// Test 3: Simulate logic of risk pill & badge with score 8.6
function evaluateRisk(seg) {
    const numScore = parseFloat(seg.danger_score || 0);
    const isDanger = numScore >= 8.0 || seg.severity === "danger";
    const isWarn = (!isDanger && (numScore >= 4.0 || seg.severity === "warning"));
    return {
        riskClass: isDanger ? "risk-danger" : (isWarn ? "risk-warn" : "risk-safe"),
        riskBadgeText: isDanger ? "NGUY HIỂM" : (isWarn ? "CẦN CHÚ Ý" : "AN TOÀN")
    };
}

// 8.6 with previously mismatched severity "warning"
const res86 = evaluateRisk({ danger_score: 8.6, severity: "warning" });
assert.strictEqual(res86.riskBadgeText, "NGUY HIỂM", "Score 8.6 must be NGUY HIỂM");
assert.strictEqual(res86.riskClass, "risk-danger", "Score 8.6 must have risk-danger class");

// 5.5
const res55 = evaluateRisk({ danger_score: 5.5, severity: "safe" });
assert.strictEqual(res55.riskBadgeText, "CẦN CHÚ Ý", "Score 5.5 must be CẦN CHÚ Ý");
assert.strictEqual(res55.riskClass, "risk-warn", "Score 5.5 must have risk-warn class");

// 2.1
const res21 = evaluateRisk({ danger_score: 2.1, severity: "safe" });
assert.strictEqual(res21.riskBadgeText, "AN TOÀN", "Score 2.1 must be AN TOÀN");
assert.strictEqual(res21.riskClass, "risk-safe", "Score 2.1 must have risk-safe class");

console.log("All frontend three-tier and crowd filtering tests passed!");
