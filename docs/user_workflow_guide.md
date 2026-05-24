# OpenSignal ITS - User Workflow Guide

## Purpose
OpenSignal ITS is a **lightweight, self-hosted** web application for traffic professionals to remotely monitor and control traffic signal controllers and connected cabinet equipment.

It is intentionally simpler and more focused than full commercial ATMS platforms.

## Target Users
- Traffic engineers and technicians at smaller agencies or consulting firms
- Users with limited budgets or niche/one-off needs
- Anyone who wants a quick-to-deploy, easy-to-learn, and extensible tool

## Core Philosophy
Open → See status at a glance → Click to investigate → Take safe action when needed.

## Terminology Baseline (Final)

The project now uses controller-centric naming consistently:

- Controller Status
- Controllers
- Access
- Alarms & Events

Authoritative label decisions and disposition of proposed alternatives are maintained in [ui-label-glossary.md](ui-label-glossary.md).

---

## Typical Daily Workflow

### 1. Open the Application
- Navigate to the web URL.
- You land on the main dashboard/workspace shell.

### 2. Main Dashboard (High-Level Overview)
- Top status bar showing selected controller, online/offline state, alarm count, and last update.
- Workspace tabs for **Controller Status**, **Signal Control**, **Maintenance**, **Alarms & Events**, **Controllers**, and **Access**.
- Quick path to **Controllers** for profile management.

**Reference:** See [ui-label-glossary.md](ui-label-glossary.md) for definitions of status indicators and summary fields.

### 3. Investigate an Intersection
- Select a controller from the controller list/profile set.
- Review live state and polling output in **Controller Status**.

### 4. Intersection Detail Page
The current **Controller Status** workspace provides day-to-day operations:

- **Header**: Controller identity, current pattern, overall status.
- **Live Phase Diagram** (visual): Shows real-time phase indications mapped to actual movements.
- **Real-Time Status**: Current greens/reds, active vehicle/pedestrian calls, timers.
- **Control Panel**: Safe commands (pattern change, mode selection, manual hold/advance) with confirmations.
- **Tabs** (lower section):
  - Logs / Events
  - Video Feeds (future)
  - Timing Plan Details
  - Raw Data / Advanced (for troubleshooting)

**Reference:** Many fields on this page are defined in [ui-label-glossary.md](ui-label-glossary.md). Not all labels need to be displayed prominently in the final UI; technical/raw fields can be hidden behind an "Advanced" or "Raw Data" tab.

### 5. Controller Management
- Navigate to **Controllers** (sidebar or top nav).
- Add, edit, or remove signal controllers.
- Configure basic metadata (IP address, SNMP settings, location, phase-to-movement mapping).

### 6. Alarms & Notifications
- Critical alarms appear on the main dashboard and detail pages.
- (Future enhancement) Email or persistent in-app notifications.

---

## Important Notes on Current UI
- The existing UI contains some technical labels and fields (see [ui-label-glossary.md](ui-label-glossary.md)).
- Not every field currently shown needs to remain visible in the final interface.
- We will gradually simplify the UI to focus on operator-useful information while keeping advanced/raw data accessible but out of the way.
- A map-first controller selection panel is now implemented as a preview scaffold and can be upgraded to full GIS mapping.

---

**Document Status**: Draft v2  
**Last Updated**: 2026-05-23  
**Intended Audience**: Developers, new users, and stakeholders
