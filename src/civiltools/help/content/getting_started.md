---
id: getting_started
title: Getting Started
title_fa: شروع کار
context: help.getting_started
order: 2
---

# Getting Started

## Installation

### From Source (Development)

```bash
# Create conda environment
conda create -n civiltools python=3.12 pythonocc-core=7.9 -c conda-forge
conda activate civiltools

# Clone and install
cd G:\civiltools
pip install -e ".[dev]"
```

### Standalone Executable

Download the latest release from the distribution site and run the installer.
No Python installation required.

## First Launch

1. **Trial Period**: On first launch, a 30-day trial begins automatically.
2. **Activation**: After trial, enter a serial key in the activation dialog.
3. **Main Window**: The application opens with the 3D viewer, story panel, and
   menu bar ready for use.

## Creating a New Model

1. Go to **File → New Model** or press `Ctrl+N`
2. Define stories in the **Story Panel** (right dock)
3. Add grid axes via **Edit → Grid Axes**
4. Add structural elements through the toolbar

## Importing from ETABS

1. Open your model in ETABS first
2. In civilTools, go to **File → Import from ETABS**
3. The application will connect via COM API and import the model

## Keyboard Shortcuts

| Action             | Shortcut       |
|--------------------|----------------|
| New Model          | `Ctrl+N`       |
| Open Model         | `Ctrl+O`       |
| Save Model         | `Ctrl+S`       |
| Generate Report    | `Ctrl+R`       |
| Toggle Help Panel  | `F1`           |
| Fit All (Viewer)   | `V`            |
| Top View           | `Numpad 7`     |
| Front View         | `Numpad 1`     |
| Right View         | `Numpad 3`     |
