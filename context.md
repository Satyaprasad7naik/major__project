Here's a clean, professional `context.md` you can drop into the repo root (or give directly to Antigravity). It is written specifically so an AI agent can redesign the frontend properly.

```markdown
# Context: Mixo / InsightOS – Professional Frontend Redesign

## 1. Project Overview

**Product Name:** Mixo (also known as InsightOS / DerivInsight)  
**Type:** Autonomous Retail Decision Engine & AI Intelligence Platform  
**Core Value:** Transforms retail data into Finding → Insight → Recommended Action with zero external LLM dependency for core logic.

### What the system does
- Natural Language → SQL + Executive Insights
- Custom offline ML models: Intent Classifier, Demand Forecaster, Stockout Risk Engine, Reorder Calculator
- Live multi-source data sync (Tally ERP, Google Sheets, Excel/Network folders)
- Autonomous procurement workflow (DRAFT → APPROVED → SENT Purchase Orders)
- Proactive Auto Insights (stockout risk, sales drop, high-risk items)
- Scope 1-3 Carbon Accounting

**Primary Users:** Category Managers, Retail Executives, Inventory Planners, Operations teams.

---

## 2. Current Frontend State

There are three frontend implementations:

| Folder            | Tech Stack                  | Status                  | Notes |
|-------------------|-----------------------------|-------------------------|-------|
| `frontend/`       | Vanilla HTML + CSS + JS     | Main working version    | Cyber cyan/purple theme, glassmorphism |
| `frontend-react/` | React 18 + Vite + TypeScript| More structured         | Chat + Sentinel dual mode |
| `frontend-next/`  | Next.js + Tailwind          | Experimental            | Project 2 hub |

**Current Visual Style:**
- Dark cyber theme (cyan `#00e5ff` + purple)
- Glassmorphism + glowing effects
- Already uses relatively sharp corners (2–4px radius)
- Background grid + floating orbs

**Problems with current design:**
- Feels more “hacker/tooling” than professional enterprise product
- Color palette does not feel retail/executive ready
- Inconsistent spacing and hierarchy across modes
- Not optimized for long executive sessions

---

## 3. Redesign Goals (Very Important)

### Primary Goal
Create a **professional, high-trust, executive-grade interface** that still feels high-tech and modern.

### Design Direction
**Theme Name:** Orange Command  
**Style:** High-tech Squared / Industrial Precision

**Key Characteristics:**
- Pure black / near-black base
- Vivid orange as the single strong accent
- Extremely sharp geometry (almost no border-radius)
- Clean, dense information hierarchy
- Minimal but purposeful motion
- Feels like a modern command center for retail executives

### Color System (Strict)

```css
/* Core */
--bg-primary:        #050505;
--bg-secondary:      #0A0A0A;
--bg-tertiary:       #111111;
--bg-elevated:       #161616;

/* Accent */
--orange-500:        #FF6B00;   /* Primary brand */
--orange-400:        #FF8C00;   /* Hover / lighter */
--orange-600:        #E55A00;   /* Pressed */
--orange-glow:       rgba(255, 107, 0, 0.22);

/* Text */
--text-primary:      #F5F5F5;
--text-secondary:    #A3A3A3;
--text-muted:        #666666;
--text-inverse:      #050505;

/* Semantic */
--success:           #00C853;
--warning:           #FFAB00;
--critical:          #FF1744;
--info:              #2979FF;

/* Borders */
--border-subtle:     rgba(255, 107, 0, 0.12);
--border-default:    rgba(255, 107, 0, 0.22);
--border-strong:     rgba(255, 107, 0, 0.45);
```

### Typography
- UI Font: Inter or system-ui
- Data / Code / Metrics: JetBrains Mono or Fira Code
- Strong hierarchy with uppercase micro-labels + increased letter-spacing

### Geometry Rules
- Border radius: **0px – 3px maximum** (prefer 2px)
- Prefer sharp rectangles and clear geometric separation
- Thin 1px orange accent lines under section headers
- Left accent bar on active items and priority cards

---

## 4. Information Architecture (Keep These Modes)

The product has three main modes. Redesign must preserve them:

1. **Query Assistant** (Natural Language Chat)
2. **Sentinel Mode** (Autonomous monitoring dashboard)
3. **Auto Insights** (Proactive alerts board)

Recommended top-level structure:

```
Header (Logo + Mode Tabs + Live Status)
├── Left Sidebar (Controls, Domain, Examples, Sync Status)
├── Main Workspace (changes based on active mode)
└── Right Panel (optional – Results / Details / Actions)
```

---

## 5. Key Screens to Redesign

### A. Query Assistant
- Clean chat interface with sharp message cards
- SQL preview block (black background + orange border + mono font)
- Insight cards using the pattern: **Finding → Insight → Recommended Action**
- Results table + charts

### B. Sentinel Dashboard
- 3-column sharp grid layout
- Severity-coded cards (Critical / High / Medium / Low)
- Mini charts + one-click actions
- Live “last scan” indicator

### C. Auto Insights Board
- Prioritized alert feed
- Severity chips + product context
- Mark as read / Take action buttons
- Empty state that feels professional

### D. Global Elements
- Header with logo + navigation + connection status
- Sidebar with domain selector and quick examples
- Sync status indicators (Tally / Google Sheets / Network)
- Risk tier summary

---

## 6. Component Design Principles

- **Cards:** Solid dark background, 1px orange border, thin top accent line
- **Buttons:** Primary = solid orange, Secondary = outline orange, Ghost = text only
- **Tables:** Orange header row, alternating subtle rows, sharp corners
- **Status Indicators:** Small square or sharp pill with left color bar
- **Inputs:** Black background, thin orange border on focus, mono for technical fields
- **Charts:** Orange primary series, dark background, minimal grid

---

## 7. Technical Constraints & Preferences

- Prefer keeping the existing React (`frontend-react`) or Next.js structure if possible
- Vanilla version can also be upgraded if faster
- Must remain fully functional with current FastAPI backend (`localhost:8080`)
- Responsive but desktop-first (executives mainly use large screens)
- Accessibility: good contrast, keyboard navigation, clear focus states
- Performance: avoid heavy blur/glass effects that hurt performance

---

## 8. Success Criteria for the Redesign

A successful redesign should feel:

- Professional enough for a retail executive presentation
- High-tech and precise (not playful or consumer-app like)
- Highly scannable (important numbers and risks jump out)
- Consistent across all three modes
- Easy to extend with new modules later

**Avoid:**
- Soft rounded cards
- Heavy glassmorphism
- Multiple competing accent colors
- Decorative illustrations that reduce information density
- Overly playful icons or animations

---

## 9. Suggested Implementation Order

1. Design system (colors, typography, spacing, base components)
2. Global layout (Header + Sidebar + Main area)
3. Query Assistant mode
4. Sentinel Dashboard
5. Auto Insights board
6. Polish (loading states, empty states, micro-interactions)

---

## 10. Brand Personality

**Mixo should feel like:**
> “A precise, high-stakes command center for retail decision makers — calm under pressure, extremely clear, and always action-oriented.”

Tone keywords: Precise • Authoritative • Modern • Dense • Reliable

---

**End of Context**

Use this document as the single source of truth when redesigning any part of the Mixo / InsightOS frontend.
```

---

### How to use it with Antigravity

1. Save the content above as `context.md` in the project root (or replace the existing one).
2. In Antigravity, reference it clearly, for example:

```text
Using the context.md file, redesign the entire frontend of Mixo/InsightOS 
following the Orange Command high-tech squared design system. 
Start with the global layout and design system, then redesign the Query Assistant mode.
```
