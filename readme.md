# 3psLCCA — Installation Guide

## Requirements

- Python >= 3.12

---

## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv venv
```

**Windows:**
```bash
venv\Scripts\activate
```

**macOS / Linux:**
```bash
source venv/bin/activate
```

---

### 2. Clone the repository

```bash
git clone -b master-con https://github.com/swas02/3psLCCA-gui.git
cd 3psLCCA-gui
```

---

### 3. Clone the core engine

```bash
git clone https://github.com/swas02/3psLCCA-core.git
```

This places `3psLCCA-core/` inside the project root, where `requirements.txt` expects it.

---

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

This installs all packages including `3psLCCA-core` as a local editable install.

---

### 5. Run the application

```bash
python -m gui.main
```

> Run all commands from the project root — the folder containing `gui/`.

---

## Project Structure

```
3psLCCA-gui/
├── 3psLCCA-core/       # Core LCCA engine (cloned separately)
├── gui/
│   └── main.py
├── core/
├── data/
├── scripts/
├── user_projects/
└── requirements.txt
```
