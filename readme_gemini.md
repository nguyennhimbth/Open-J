# Open-J: Open-Source Jeopardy! Game Show Engine

**Open-J** is a modular, event-driven game show engine and production system designed to faithfully recreate and simulate the iconic game show **Jeopardy!** in accordance with official broadcast standards (Season 40 & 41 specifications).

Developed using **Python 3.12+**, **PySide6 (Qt for Python)**, and **SQLite**, Open-J features an asynchronous decoupled architecture that separates the core game mechanics, question database, scoring engines, media assets, and upcoming studio presentation displays.

---

## Table of Contents

1. [Jeopardy! Game Rules & Mechanics](#jeopardy-game-rules--mechanics)
2. [Codebase Architecture & Directory Structure](#codebase-architecture--directory-structure)
3. [Deep Dive: Core Engines & Subsystems](#deep-dive-core-engines--subsystems)
   - [Event Bus (core/core_eventbus.py)](#1-event-bus-corecore_eventbuspy)
   - [Question Engine (core/question_core.py)](#2-question-engine-corequestion_corepy)
   - [Score Engine (core/score_core.py)](#3-score-engine-corescore_corepy)
   - [Main Orchestrator (main.py)](#4-main-orchestrator-mainpy)
4. [Data Storage & Assets](#data-storage--assets)
5. [Installation & Getting Started](#installation--getting-started)
6. [Roadmap & Planned Features](#roadmap--planned-features)

---

## Jeopardy! Game Rules & Mechanics

The engine's logic is modeled directly after the official rules codified in `rules.md`:

### 1. General Game Format
- **3 Contestants** (`p1`, `p2`, `p3`) compete across **3 main rounds**.
- **Response Phrasing**: All contestant answers must strictly be phrased in the form of a question (*"What is...?"* or *"Who is...?"*).

### 2. Round 1: Jeopardy! Round
- **Grid Setup**: 6 Categories $\times$ 5 Clue tiers (Point values: **$200, $400, $600, $800, $1,000**).
- **Buzzer Lockout System**:
  - The host reads the clue completely before buzzers are enabled.
  - First contestant to signal earns the right to answer.
  - Buzzing in prematurely (*"jumping the gun"*) triggers a **0.25-second lockout penalty**.
  - Contestants have **5 seconds** to provide a response upon being recognized.
- **Scoring**:
  - **Correct**: Adds the clue's value to the contestant's score; winner assumes board control.
  - **Incorrect / Out of Time**: Deducts the clue's value (scores can drop below zero). Remaining contestants may buzz in on rebound.
- **Daily Double**: Exactly **1 Daily Double** is hidden randomly on the board.
  - Only the selecting contestant can respond (buzzers are disabled).
  - Minimum wager: **$5**.
  - Maximum wager: **$1,000** if score $\le \$1,000$; or the player's **entire current score** if $> \$1,000$ (*True Daily Double*).

### 3. Round 2: Double Jeopardy! Round
- **Grid Setup**: 6 brand-new Categories $\times$ 5 Clue tiers.
- **Doubled Point Values**: **$400, $800, $1,200, $1,600, $2,000**.
- **Board Control**: The contestant with the lowest score at the end of Round 1 chooses the first clue.
- **Daily Doubles**: Exactly **2 Daily Doubles** are hidden randomly on the board.
  - Minimum wager: **$5**.
  - Maximum wager: **$2,000** if score $\le \$2,000$; or the player's **entire current score** if $> \$2,000$.

### 4. Round 3: Final Jeopardy!
- **Eligibility**: Only contestants with a strictly positive score ($> \$0$) at the conclusion of Double Jeopardy! qualify. Contestants with $\le \$0$ are eliminated.
- **Gameplay Sequence**:
  1. **Category Reveal**: Host announces the single category.
  2. **Blind Wagers**: Contestants submit secret wagers ($0 up to their full score).
  3. **Clue & 30-Second Countdown**: Host reads the clue and triggers the 30-second music timer.
  4. **Written Submission**: Contestants write down their response in question format.
- **Final Scoring**:
  - Correct response: Adds wagered amount.
  - Incorrect or blank response: Deducts wagered amount.

### 5. Winner Determination & Consolation Payouts
- **1st Place**: Retains cumulative final score as cash earnings and returns as defending champion.
- **2nd Place**: Fixed consolation award of **$3,000**.
- **3rd Place**: Fixed consolation award of **$2,000**.

---

## Codebase Architecture & Directory Structure

```
Project_Open-J/
│
├── core/                         # Core game logic and event dispatching
│   ├── core_eventbus.py          # Decoupled PySide6 Signal/Slot event dispatcher
│   ├── question_core.py          # SQLite-backed question and board manager
│   ├── score_core.py             # Score computation, wagering, and undo manager
│   └── readme_core.md            # Core module specifications
│
├── data/                         # Persistent storage
│   ├── questions.db              # SQLite database containing clue boards and answers
│   └── readme_data.md            # Data layer specifications
│
├── network/                      # Networking and multiplayer protocols (in development)
│   └── readme_network.md         # Network communication architecture
│
├── ui/                           # Graphical user interface and multimedia assets
│   ├── assets/
│   │   ├── image/                # Visual clue media (e.g., portraits, diagrams)
│   │   └── sounds/               # Sound effects (buzzers, timer, daily double)
│   └── readme_ui.md              # UI/UX design specifications
│
├── main.py                       # Main application entry point & gameplay simulator
├── requirements.txt              # Project Python dependencies
├── rules.md                      # Official Jeopardy! rulebook (Season 40 & 41)
├── readme_gemini.md              # Comprehensive project documentation
└── README                        # Standard repository readme pointer
```

---

## Deep Dive: Core Engines & Subsystems

### 1. Event Bus (`core/core_eventbus.py`)
The system utilizes a decoupled publish-subscribe pattern built on Qt's signal/slot infrastructure (`QObject` and `Signal`). Components communicate through `event_bus` without direct coupling:

| Signal | Arguments | Description |
|---|---|---|
| `request_open_question` | `(round_id: int, col_index: int, row_index: int)` | Emitted by the UI/Host to open a specific board tile. |
| `display_question` | `(question_data: dict)` | Broadcasts question details and media paths to display screens. |
| `close_question` | `()` | Closes the current clue and returns focus to the game board. |
| `trigger_daily_double` | `(player_id: str, max_wager: int)` | Triggers the Daily Double wagering sequence for the eligible player. |
| `modify_score` | `(player_id: str, points: int, is_correct: bool)` | Requests a score update based on contestant answer validity. |
| `score_updated` | `(all_scores: dict)` | Broadcasts the updated scores of all 3 contestants to all views. |
| `change_round` | `(round_id: int)` | Transitions the game state between Round 1, Round 2, and Round 3. |

### 2. Question Engine (`core/question_core.py`)
Handles all database operations via SQLite (`data/questions.db`):
- **Database Schema**:
  ```sql
  CREATE TABLE questions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      round_id INTEGER NOT NULL,          -- 1: Jeopardy, 2: Double Jeopardy, 3: Final
      col_index INTEGER NOT NULL,         -- Category column (0-5)
      row_index INTEGER NOT NULL,         -- Value row (0-4)
      category_name TEXT NOT NULL,       -- Category title
      points INTEGER NOT NULL,            -- Base clue value ($200 - $2000)
      question_text TEXT NOT NULL,        -- The clue presented to contestants
      answer_text TEXT NOT NULL,          -- Correct response (host view only)
      asset_filename TEXT DEFAULT '',     -- Optional clue image filename
      is_daily_double BOOLEAN DEFAULT 0,  -- 1 if Daily Double tile
      is_used BOOLEAN DEFAULT 0           -- 1 if already played
  );
  ```
- **Asset Fallback Resolution**: Automatically resolves visual media from `ui/assets/image/`. If a referenced image is missing or empty, `has_asset` safely flags `False`.
- **Sample Data Seeding**: Populates sample questions for Round 1, Round 2 (with 2 Daily Doubles), and Round 3 (Final Jeopardy!).

### 3. Score Engine (`core/score_core.py`)
Manages contestant balances and state transitions:
- **Players Initialized**: Defaults to `p1`, `p2`, `p3` (e.g., Ken Jennings, Gold Ship, Agnes Tachyon).
- **Score Calculation**:
  - `add_correct(player_id, points)`: Increases score on correct answer.
  - `add_incorrect(player_id, points)`: Decreases score on incorrect answer (supports negative balances).
  - `apply_wager(player_id, wager_amount, is_correct)`: Processes Daily Double and Final Jeopardy bets.
- **Undo Stack (`undo_last_action`)**: Maintains an operation history list allowing the host to instantly revert score adjustments made by accidental clicks or overturned rulings.

### 4. Main Orchestrator (`main.py`)
Acts as the central coordination layer:
1. Instantiates `QuestionEngine` and `ScoreEngine`.
2. Connects `event_bus` signals to their respective handler functions.
3. Provides `run_simulation()` to verify event flow, question fetching, and score tallying without requiring an active graphical display.

---

## Data Storage & Assets

- **Database (`data/questions.db`)**: Local SQLite database storing all category questions, points, flags, and usage history.
- **Images (`ui/assets/image/`)**: Clue-related graphics (portraits, diagrams, historical photographs).
- **Audio (`ui/assets/sounds/`)**: Broadcast sound effects (daily double chime, commercial countdown, buzzer lockouts, and final think music).

---

## Installation & Getting Started

### 1. Prerequisites
- Python 3.10+ (Python 3.12 recommended)
- `pip` package manager

### 2. Environment Setup
Clone or navigate to the repository directory:
```bash
cd Project_Open-J
```

Create and activate a virtual environment:
```powershell
# Windows PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Running the Gameplay Simulation
Execute `main.py` to run the test simulation:
```powershell
# Set UTF-8 encoding if running on Windows terminal
$env:PYTHONIOENCODING = "utf-8"
python main.py
```

Expected output:
```text
=== CHẠY MÔ PHỎNG GAMEPLAY QUA MAIN.PY ===

[MAIN ORCHESTRATOR] Bắn câu hỏi sang màn Studio:
- Lịch Sử ($200): Vị vua đầu tiên của nhà Tiền Lý?

[MAIN ORCHESTRATOR] Điểm số cập nhật: {'p1': 200, 'p2': 0, 'p3': 0}

[MAIN ORCHESTRATOR] Điểm số cập nhật: {'p1': 200, 'p2': -400, 'p3': 0}
```

### 4. Running Unit / Subsystem Tests
Verify individual core modules in isolation:
```bash
# Test Question Core (schema initialization, seeding, board query)
python -m core.question_core

# Test Score Core (scoring, wagering, and undo history)
python -m core.score_core
```

---

## Roadmap & Planned Features

- [x] **Core Event Bus**: Decoupled Signal/Slot pipeline.
- [x] **Question Engine**: SQLite database schema with Daily Double support and 3-round board queries.
- [x] **Score Engine**: Accurate scoring rules with negative totals, wagers, and undo capabilities.
- [ ] **UI Layer (`ui/`)**:
  - Studio Display: Full-screen interactive board matrix with clue animations.
  - Host Console: Clue answers, buzzer state controls, score override tools, and timer indicators.
  - Contestant Podiums: Real-time score displays, wager input panels, and buzzer status indicators.
- [ ] **Network & Buzzer Subsystem (`network/`)**:
  - WebSocket / TCP buzzer lockout engine with millisecond timing resolution.
  - 0.25-second false-start lockout penalty enforcement.
  - Mobile / Web client buzzer integration for physical contestant remotes.
- [ ] **Question Pack Tooling (`data/`)**:
  - Web/CLI tool to import/export questions from J-Archive or JSON/CSV formats.

