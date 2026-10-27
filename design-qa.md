# VAT-AI blue UI — design QA

Date: 2026-10-27. Base: `track-fullstack` at `03536139b3ac7083c598e06dc376ce0051103a48`. Working branch: `codex/vat-blue-ui`.

final result: passed

No actionable P0/P1/P2 visual findings remain in the reviewed states. This is a visual adaptation to VAT-AI, not a pixel-identical MoonPay clone or a certification of all backend functionality.

## Target and intentional differences

User direction: preserve VAT-AI functions, routes, button actions, API/state/data structures; apply the supplied MoonPay visual language, replacing black primary buttons with blue. White surfaces, black typography, pale gray cards, generous spacing and rounded controls are the target. Existing VAT content, navigation order, validation and semantic warning/error colors remain authoritative.

Source visual truth: `C:/Users/Master/AppData/Local/Temp/`:

- `codex-clipboard-289657d7-8631-44a6-b635-30dbf1f95288.png` — dashboard.
- `codex-clipboard-a941fde7-b84b-4f6a-8efa-d4ee81ce8064.png` — balance detail.
- `codex-clipboard-660b91ba-fc7d-402e-ace1-569c302a7631.png` — sheet and primary CTA.
- `codex-clipboard-a2d81257-05e9-43f8-98c4-8e7217a246ac.png` — status timeline.
- `codex-clipboard-2de7cee6-a26e-4400-8c1c-0a0886262b04.png` — splash; no new splash introduced.

MoonPay branding, crypto assets, Apple Pay, iOS system chrome and the Mobbin reference footer are not VAT-AI product features and were not copied. No new mock data, dependencies or localStorage code was added. Existing application storage behavior remains unchanged.

## Rendered evidence and normalization

Implementation: `http://127.0.0.1:4173`, isolated local API `http://127.0.0.1:18791`. Existing QA account authenticated with user approval against a copy of the existing database. The original database was not modified. Missing business profile means the real dashboard says “확인 필요”; no numerical state was fabricated.

All evidence below is in `outputs/ui-blue-design/` under the project root (local generated files, Git-ignored).

| Evidence | CSS viewport | Capture pixels / state |
| --- | --- | --- |
| `dashboard-final-390.jpg` | 390 × 844, DPR 1 | 375 × 812; authenticated, 2026-H2, existing estimate unavailable |
| `period-final-390.jpg` | 390 × 844, DPR 1 | 375 × 812; period sheet open, 2026-H2 selected |
| `purchase-390.jpg`, `detail-390.jpg`, `report-390.jpg`, `processing-390.jpg` | 390 × 844 | 375 × 812; local QA data |
| `purchase-320.jpg`, `receipt-edit-320.jpg`, `signup-320.jpg` | 320 × 740 | 305 × 705; narrow layout |
| `receipt-review-desktop.jpg` | 1280 × 900 | 1265 × 889; two-column review |
| `login-390.jpg` | 390 × 844 | 390 × 844; unauthenticated |

Source images are 1179 × 2676 pixels. Their original CSS size/density is not supplied. The browser screenshot provider resizes captures; measured CSS viewport and image pixels are therefore recorded separately. Combined comparisons preserve aspect ratio and normalize to equal panel widths. Source full views crop y=155..2555 to remove iOS status bar and Mobbin footer. Content, auth and interaction states differ by product intentionally; do not infer pixel-level equivalence.

- Full-view combined input inspected: `reference-comparison.jpg`, containing source dashboard + VAT dashboard and source sheet + VAT period sheet together.
- Focused combined input inspected: `controls-comparison.jpg`, source black CTA beside implementation blue CTA, with readable label, pill shape and surrounding spacing.
- User-facing overview: `preview.jpg`, three actual implementation screenshots.
- Earlier `dashboard-390.jpg` / `period-390.jpg` filenames refer to 320px captures; use the `final-390` files above as final evidence.

## Fidelity review

- **Typography:** existing system/Pretendard fallback stack retained, with Korean system fallback expected to differ from the Latin iOS source. Large, bold primary values and smaller gray metadata reproduce the hierarchy. Korean title wrapping and close-control alignment checked at 320px. No external font dependency introduced.
- **Spacing/layout:** white canvas, 24px mobile margins, 24–28px card radii, pill controls, larger section gaps and low elevation. Sheet upper corners and background dimming follow the reference. VAT's additional intro and tax-period controls intentionally place summary content farther down. Bottom navigation reserves space, including safe-area inset. Desktop receipt review retains two columns.
- **Colors/tokens:** primary `#2463eb`, hover `#194dcc`, main text `#111113`, muted surfaces `#f5f5f6`. Browser computed OCR button background verified `rgb(36, 99, 235)` and height 58px. Green indicates readiness/completion; warning/error states retain distinct semantics. Dark report balance surface is intentional; black primary CTA treatment is replaced with blue.
- **Images/assets:** existing vector Icon component and existing receipt images retained. MoonPay and crypto imagery are not applicable to VAT-AI. No generated decorative substitutions. Screenshot softness comes from provider scaling and should not be treated as source asset degradation.
- **Copy/content:** existing Korean labels, amounts, errors, disabled conditions and tax caveats retained. Headings use semantic h1 markup where revised. No design prompt text is exposed in the product.
- **Controls/accessibility:** primary controls 56px, small controls at least 44px; transaction checkbox label enlarged to 44px. Visible focus ring and selected/disabled states preserved. Observed narrow pages have no horizontal overflow. Existing focus trap/Escape behavior retained. This was a targeted visual/accessibility check, not a full screen-reader audit.

## Findings and comparison history

1. P2, transaction detail header: long Korean heading wrapped the close button onto its own row. Evidence: `detail-before-fix-390.jpg`. Fixed the heading flex sizing and nonshrinking close control. Post-fix capture `detail-390.jpg` at the same viewport shows the heading and close button aligned.
2. P2, 320px receipt header: symmetrical columns with two actions split the title excessively. Fixed only the narrow two-action header grid; retained centered normal-width layout. Post-fix `receipt-edit-320.jpg` shows readable title and available actions.
3. P2, transaction selection: native checkbox alone had a small target. Wrapped the unchanged input/handler with a 44px label; verified label dimensions and selection behavior. Post-fix `purchase-320.jpg`.
4. Camera contrast preventive adjustment: scoped neutral header icons for the existing dark capture screen and blue active shutter. Camera permission and hardware capture remain untested; no camera behavior was changed.

Final combined full-view and focused comparisons found no additional actionable P0/P1/P2 differences against the agreed visual direction. Intentional product, language and state differences are listed above. No pixel-perfect match is claimed.

## Functional verification

Verified through existing UI and isolated local API:

- Approved test-account login; dashboard data loading and amount visibility toggle.
- Period sheet open, select/confirm and close; query period retained. Rechecked after server restart.
- Dashboard review shortcut to filtered storage, purchase/sales tabs, month filter, amount sorting and transaction selection.
- Transaction detail opening and Escape dismissal; receipt edit/review navigation and basic/full details toggle.
- Existing completed OCR processing state and redirect to review; no new OCR job submitted.
- Menu/report navigation, OCR picker opening/closing, empty trash and account page.
- Signup and password-recovery entry navigation without creating accounts or resetting credentials.
- Narrow 320px forms/storage and desktop receipt review layout.

Final code checks:

- `npm run build`: passed, TypeScript + Vite, 135 modules.
- `npm run lint`: passed with 10 existing warnings in effect/export rules; no new logic changed to suppress warnings.
- `node --test tests/*.test.mjs`: 6 passed, 0 failed.
- `git diff --check`: passed.
- Reviewed TSX diff: presentation classes, headings/icons and checkbox label wrapper only; existing handlers, routes, API calls and state logic retained. Backend source unchanged.

Console check: retained log entries contain a Vite HMR WebSocket disconnect at 00:53:27 UTC while preview servers were stopped. After restarting and reloading, account API responses were 200 and the dashboard/period flow worked; no newer console error entries appeared. This is a development-server lifecycle issue, not an observed application flow failure.

## Test gaps and handoff

Real camera capture, external OCR/LLM calls, report PDF generation and production deployment were not exercised. Existing QA profile conditions disable report generation; those conditions were preserved. Visual QA passes for the reviewed states only.

- [x] Source and rendered implementation compared together.
- [x] Focused control comparison inspected.
- [x] Small-screen findings corrected and recaptured.
- [x] Existing local flows and frontend checks verified.
- [x] Local preview retained for review; temporary viewport override reset.
- [x] Initial QA was completed locally, before the user's later request to commit to `track-fullstack`. No production deployment performed.

## Follow-up: login branding

Replaced the login folder icon with the user-provided `frontend/public/vat-ai-logo.png` and centered the logo, VAT-AI heading and description. Original image proportions are preserved. Rendered evidence: `outputs/ui-blue-design/login-centered-logo.jpg`. Browser inspection confirmed successful image loading, matching logo/intro horizontal centers, and centered text. The subsequent production build and `git diff --check` passed; authentication handlers remain unchanged.
