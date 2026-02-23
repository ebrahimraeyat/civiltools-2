# Live Load Management - Quick Start Guide

## Installation

The live load management system is part of CivilTools and requires no additional installation steps.

```bash
cd g:\civiltools
pip install -e ".[dev]"
```

## Quick Examples

### 1. Work with the Database

```python
from civiltools.building import LiveLoadDatabase

db = LiveLoadDatabase()

# Get a live load value
load = db.get_load("office_general")
print(f"Office load: {load} kN/m²")

# List all available types
for use_id, name in db.list_use_types_with_names().items():
    print(f"{use_id}: {name}")
```

### 2. Create a Simple Project

```python
from civiltools.building import (
    LiveLoadDatabase,
    Project,
    Floor,
    Area,
    Point,
)

db = LiveLoadDatabase()

# Create project
project = Project("proj_001", "My Building")

# Create floor with default use
floor = Floor("floor_1", "Ground Floor", default_use="office_general")

# Add an area (no explicit use type = inherits from floor)
area = Area(
    area_id="room_101",
    geometry=[Point(0, 0), Point(10, 0), Point(10, 5), Point(0, 5)],
)
floor.add_area(area)

# Add floor to project
project.add_floor(floor)

# Get the live load
load_info = floor.get_area_load("room_101", db)
print(f"Live load: {load_info.value} kN/m²")
print(f"Source: {load_info.source.value}")
print(f"Notes: {load_info.notes}")
```

### 3. Read Stories from ETABS

```python
from civiltools.etabs.connection import EtabsConnection
from civiltools.building import ETABSStoryReader, LiveLoadDatabase

# Connect to ETABS
etabs_conn = EtabsConnection()
if etabs_conn.connect():
    # Create reader
    reader = ETABSStoryReader(etabs_conn.etabs)
    
    # Get all stories (sorted from top to bottom)
    stories = reader.get_sorted_stories(reverse=True, include_base=False)
    for story_name, elevation in stories:
        print(f"{story_name}: {elevation} m")
    
    # Print summary
    reader.print_stories_summary()
    
    # Disconnect
    etabs_conn.disconnect()
```

### 4. Create Project from ETABS with Builder Pattern

```python
from civiltools.etabs.connection import EtabsConnection
from civiltools.building import ETABSProjectBuilder

etabs_conn = EtabsConnection()
if etabs_conn.connect():
    # Create builder
    builder = ETABSProjectBuilder(etabs_conn.etabs)
    
    # Configure project
    project = (builder
        .set_project_info("tower_001", "Downtown Tower")
        .apply_use_to_floor("Story1", "retail_small_ground")
        .apply_use_to_floor("Story2", "office_general")
        .apply_use_to_floor("Story3", "office_general")
        .apply_use_to_floor("Story4", "residential_rooms")
        .build())
    
    # View configuration
    builder.print_summary()
    
    etabs_conn.disconnect()
```

## Load Priority System

When you request a load for an area, the system checks in this order:

```
1. Is there a manual override? → Use it
2. Does the area have an explicit use type? → Use it
3. Does the floor have a default use type? → Use it
4. Fall back to project default → Use it
```

### Example

```python
from civiltools.building import Floor, Area, Point, LiveLoadDatabase

db = LiveLoadDatabase()
floor = Floor("f1", default_use="office_general")  # 9.0 kN/m²

# Area 1: Inherits from floor
area1 = Area("a1", [Point(0,0), Point(5,0), Point(5,5), Point(0,5)])
load1 = floor.get_area_load("a1", db)  # Returns 9.0 kN/m² (inherited)

# Area 2: Has explicit use type
area2 = Area("a2", [Point(5,0), Point(10,0), Point(10,5), Point(5,5)],
             use_type="residential_rooms")
load2 = floor.get_area_load("a2", db)  # Returns 2.0 kN/m² (explicit)

# Area 3: Manual override
area3 = Area("a3", [Point(10,0), Point(15,0), Point(15,5), Point(10,5)])
area3.set_manual_load(3.5)
load3 = floor.get_area_load("a3", db)  # Returns 3.5 kN/m² (manual)
```

## Common Use Types

| Type ID | Name | Load | Usage |
|---------|------|------|-------|
| `office_general` | General Office | 9.0 kN/m² | Standard office spaces |
| `residential_rooms` | Residential | 2.0 kN/m² | Bedrooms, living rooms |
| `retail_small_ground` | Small Retail - Ground | 4.5 kN/m² | Retail stores |
| `classroom_light_lab` | Classroom | 4.5 kN/m² | Educational spaces |
| `hospital_patient_room` | Hospital Patient Room | 4.5 kN/m² | Hospital patient areas |
| `parking_light` | Parking - Light Vehicles | 3.0 kN/m² | Car parking areas |
| `industrial_light` | Light Industrial | 9.0 kN/m² | Light manufacturing |
| `assembly_hall_no_seats` | Assembly Hall | 5.0 kN/m² | Concert halls, events |
| `roof_ordinary` | Ordinary Roof | 1.5 kN/m² | Standard roofs |

## Validation

Always validate your project before use:

```python
from civiltools.building import LiveLoadDatabase

db = LiveLoadDatabase()

# Validate all floors
warnings = project.validate_all(db)
if warnings:
    for floor_id, issues in warnings.items():
        print(f"Floor {floor_id}:")
        for issue in issues:
            print(f"  - {issue}")
else:
    print("✓ Project validation passed")

# Validate ETABS stories
reader = ETABSStoryReader(etabs_obj)
story_warnings = reader.validate_stories()
if story_warnings:
    for warning in story_warnings:
        print(f"⚠ {warning}")
```

## Getting Load Information

Each load includes metadata:

```python
load_info = floor.get_area_load("room_101", db)

print(f"Value: {load_info.value} kN/m²")
print(f"Source: {load_info.source.value}")  # "direct", "inherited_floor", etc.
print(f"Use type: {load_info.use_type}")
print(f"Notes: {load_info.notes}")
```

## Tips and Best Practices

1. **Always use LiveLoadDatabase(**):
   - Centralize all reference data
   - Ensures consistency across the project

2. **Set floor defaults** when many areas share the same use type:
   ```python
   floor.apply_default_use("office_general")
   ```

3. **Use explicit types** only when needed:
   - Reduces data entry errors
   - Easier to maintain consistency

4. **Validate before exporting**:
   ```python
   warnings = project.validate_all(db)
   if not warnings:
       # Safe to proceed
   ```

5. **Profile story info from ETABS** before assigning use types:
   ```python
   reader.print_stories_summary()
   ```

## File Locations

```
src/civiltools/building/
├── live_load_manager.py         # Core logic
├── live_load_data.json          # Live load reference data (54 use types)
├── etabs_story_reader.py        # ETABS integration
├── example_live_load.py         # Basic examples
├── example_etabs_integration.py # Advanced ETABS examples
└── README_LIVE_LOAD.md          # Full documentation
```

## Running Examples

Basic example (no ETABS required):
```bash
python -m civiltools.building.example_live_load
```

ETABS integration examples:
```bash
python -m civiltools.building.example_etabs_integration
```

## Support and Documentation

- Full documentation: `README_LIVE_LOAD.md`
- Detailed API docs in docstrings
- See examples in `example_*.py` files

## Next Steps

1. Explore the database:
   ```python
   db = LiveLoadDatabase()
   print(db.list_use_types())
   ```

2. Create a simple project and experiment with the priority system

3. Connect to an active ETABS model and read real stories

4. Integrate with your structural analysis workflow
