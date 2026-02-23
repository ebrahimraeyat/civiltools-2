# Live Load Management System

A comprehensive Python module for managing building live loads in structural analysis software (ETABS). This system provides a hierarchical data model, integration with ETABS, and support for Iranian building codes.

## Features

### Core Features
- **Hierarchical Data Model**: Project → Floor → Area structure with inheritance
- **Live Load Database**: Complete Iranian building code live load standards
- **Distributed & Concentrated Loads**: Support for both load types
- **ETABS Integration**: Direct reading of story/floor data from active ETABS models
- **Load Priority System**: Automatic load inheritance through 4-level priority chain
- **Validation Framework**: Built-in validation for structural consistency
- **Fluent API**: Easy-to-use builder pattern for project configuration

### Building Code Support
Implements Iranian Standard 2800 and INBC (Iran National Building Code) requirements for:
- Residential, commercial, and industrial spaces
- Educational and healthcare facilities
- Parking and storage areas
- Roofs and special structures
- 50+ distinct use type categories

## Module Structure

```
civiltools/building/
├── live_load_manager.py         # Core data classes and database
├── live_load_data.json          # Live load standards reference
├── etabs_story_reader.py        # ETABS integration
├── example_live_load.py         # Basic usage examples
└── example_etabs_integration.py # ETABS integration examples
```

## Core Classes

### LiveLoadDatabase
Manages the live load database and provides queryable access to standard values.

```python
from civiltools.building.live_load_manager import LiveLoadDatabase

db = LiveLoadDatabase()

# Get distributed load
load = db.get_load("office_general")  # Returns 9.0 kN/m²

# Get concentrated load
conc = db.get_concentrated_load("retail_small_ground")  # Returns 5.0 kN

# Get descriptive information
name = db.get_name("office_general")  # Returns "General Office"
desc = db.get_description("office_general")  # Returns full description

# List all available types
use_types = db.list_use_types()
```

### Area
Represents a floor space or zone within a building story.

```python
from civiltools.building.live_load_manager import Area, Point

# Create an area
area = Area(
    area_id="room_101",
    geometry=[Point(0, 0), Point(5, 0), Point(5, 3), Point(0, 3)],
    use_type="office_general"  # or None for inheritance
)

# Assign use type
area.set_use_type("residential_rooms", manual=True)

# Manually override load (ignores use type)
area.set_manual_load(2.5)  # 2.5 kN/m²

# Clear manual override
area.clear_manual_load()
```

### Floor
Represents a building story/floor with multiple areas.

```python
from civiltools.building.live_load_manager import Floor

floor = Floor(
    floor_id="ground",
    floor_name="Ground Floor",
    default_use="retail_small_ground"
)

# Add areas
floor.add_area(area1)
floor.add_area(area2)

# Apply default use to all areas without explicit type
floor.apply_default_use("office_general")

# Get area load with inheritance
load_info = floor.get_area_load("room_101", database)
print(load_info.value)      # Numeric value
print(load_info.source)     # LoadSource enum
print(load_info.notes)      # Description of source
```

### Project
Top-level container for all floors in a building.

```python
from civiltools.building.live_load_manager import Project

project = Project(
    project_id="bldg_001",
    project_name="Office Building"
)

# Add floors
project.add_floor(ground_floor)
project.add_floor(first_floor)

# Validate entire project
warnings = project.validate_all(database)
```

## Load Priority System

When retrieving a load for an area, the system follows this priority chain:

```
1. Manual Override (_manual_override)
   ↓
2. Area Use Type (area.use_type)
   ↓
3. Floor Default Use (floor.default_use)
   ↓
4. Project Default (database.get_default_load())
```

Each level is checked in order; if found, that value is used. This enables:
- Granular control when needed
- Efficient bulk assignment of default loads
- Clear tracking of load sources

## ETABS Integration

### Basic Story Reading

```python
from civiltools.building.etabs_story_reader import ETABSStoryReader
from civiltools.etabs.connection import EtabsConnection

# Connect to ETABS
etabs_conn = EtabsConnection()
if etabs_conn.connect():
    # Create reader
    reader = ETABSStoryReader(etabs_conn.etabs)
    
    # Get sorted stories
    stories = reader.get_sorted_stories(reverse=True, include_base=False)
    # Returns: [('Story4', 12.0), ('Story3', 9.0), ('Story2', 6.0), ('Story1', 3.0)]
    
    # Get story names only
    names = reader.get_story_names()
    
    # Get comprehensive story info
    info = reader.get_all_stories_info()
    # Returns dictionary with elevation, height, element counts, etc.
    
    # Print summary
    reader.print_stories_summary()
```

### Project Builder Pattern

For complex projects, use the fluent builder interface:

```python
from civiltools.building.etabs_story_reader import ETABSProjectBuilder

builder = ETABSProjectBuilder(etabs_obj)
project = (builder
    .set_project_info("office_tower", "Downtown Office Tower")
    .apply_use_to_floor("Story1", "retail_small_ground")
    .apply_use_to_floor("Story2", "office_general")
    .apply_use_to_floor("Story3", "office_general")
    .apply_use_to_floor("Story4", "residential_rooms")
    .build())

# Review configuration
builder.print_summary()
```

## Usage Examples

### Example 1: Basic Project Creation

```python
from civiltools.building.live_load_manager import (
    Project, Floor, Area, Point, LiveLoadDatabase
)

# Create database
db = LiveLoadDatabase()

# Build project
project = Project("proj_001", "Sample Building")

# Create floor
floor = Floor("ground", "Ground Floor", default_use="office_general")

# Add areas
area1 = Area("area1", [Point(0,0), Point(10,0), Point(10,10), Point(0,10)])
floor.add_area(area1)

project.add_floor(floor)

# Get loads
load_info = floor.get_area_load("area1", db)
print(f"Load: {load_info.value} kN/m² (from {load_info.source.value})")
```

### Example 2: Mixed-Use Building

```python
# Residential lower floors, offices middle, retail ground
ground = Floor("story1", "Ground", default_use="retail_small_ground")
office_1 = Floor("story2", "Office 1", default_use="office_general")
office_2 = Floor("story3", "Office 2", default_use="office_general")
residential = Floor("story4", "Residential", default_use="residential_rooms")

project = Project("mixed_use", "Mixed-Use Building")
for floor in [ground, office_1, office_2, residential]:
    project.add_floor(floor)

# Validate
warnings = project.validate_all(db)
```

### Example 3: ETABS Integration

```python
from civiltools.etabs.connection import EtabsConnection
from civiltools.building.etabs_story_reader import ETABSProjectBuilder

# Connect and read
etabs_conn = EtabsConnection()
etabs_conn.connect()

# Build project from ETABS
builder = ETABSProjectBuilder(etabs_conn.etabs)
project = (builder
    .set_project_info("from_etabs_001", etabs_conn.model_path)
    .apply_default_use_to_all("office_general")
    .build())

# Use with live load system
db = LiveLoadDatabase()
for floor in project.floors.values():
    for area_id in floor.areas.keys():
        load = floor.get_area_load(area_id, db)
        print(f"{area_id}: {load.value} kN/m²")

etabs_conn.disconnect()
```

## Load Source Types

Each load has an associated source for tracking and verification:

```python
from civiltools.building.live_load_manager import LoadSource

LoadSource.DIRECT              # Manually set on area
LoadSource.INHERITED_FLOOR     # From floor's default_use
LoadSource.INHERITED_PROJECT   # From project default
LoadSource.CALCULATED          # Computed (e.g., balconies)
```

## Data Model Visualization

```
Project
├── Floor (Story1)
│   ├── default_use: "office_general"
│   └── Area (room_101)
│       ├── use_type: None → inherits from floor
│       └── live_load: 9.0 kN/m² (inherited)
│
├── Floor (Story2)
│   ├── default_use: "residential_rooms"
│   └── Area (apt_201)
│       ├── use_type: "residential_rooms"
│       └── live_load: 2.0 kN/m² (direct)
│
└── Floor (Story3)
    ├── default_use: None
    └── Area (special_lab)
        ├── use_type: "classroom_light_lab" (explicitly set)
        └── live_load: 4.5 kN/m² (direct)
```

## Available Use Types

The database includes 50+ standard use types based on Iranian building codes:

### Structural Categories
- **Roofs**: ordinary, light covering, garden, fabric structures
- **Residential**: private rooms, hotels, dormitories
- **Commercial**: retail, wholesale, offices
- **Industrial**: light, medium, heavy workshops
- **Public**: assembly halls, theaters, restaurants, mosques
- **Educational**: classrooms, study rooms, libraries (fixed/mobile shelves)
- **Healthcare**: patient rooms, operating rooms, corridors
- **Special**: parking, kitchens, elevators, mechanical rooms, storage, helipads

### Key Features of Database
- Distributed loads (kN/m²)
- Concentrated point loads (kN) where applicable
- Clear descriptions and use case guidelines
- Non-reducible load flags for code compliance
- Per-height supplements for storage and library spaces

## Validation

### Story Validation (ETABS Reader)
```python
warnings = reader.validate_stories()
# Checks for:
# - Unusual story heights
# - Empty stories with no elements
# - Configuration consistency
```

### Project Validation
```python
warnings = project.validate_all(db)
# Checks for:
# - Empty floors
# - Unassigned use types on floors with no default
# - Structural consistency
```

## Configuration

### Environment Variables

To use a non-default location for etabs_api:
```bash
set ETABS_API_PATH=C:\path\to\etabs_api\src
```

### pyproject.toml Setup

```toml
[project.optional-dependencies]
dev = [
    "etabs_api @ file:///C:/Users/ebrahim/AppData/Roaming/FreeCAD/Mod/etabs_api",
]

[tool.hatch.metadata]
allow-direct-references = true
```

## Error Handling

The system provides clear error messages:

```python
try:
    load = db.get_load("invalid_type")
except ValueError as e:
    print(e)  # "Unknown use type: invalid_type. Available types: ..."

try:
    load = floor.get_area_load("nonexistent_area", db)
except ValueError as e:
    print(e)  # "Area nonexistent_area not found in floor ..."
```

## Type Hints

Full Python type hints for IDE support:

```python
def get_area_load(
    area_id: str,
    database: LiveLoadDatabase,
) -> LoadInfo:
    ...
```

## Performance Considerations

- In-memory data structures optimized for typical building sizes (10-50 floors)
- O(1) area lookup within floors
- O(n) for floor/story queries (typically n < 50)
- Minimal memory footprint (~1KB per area)

## Testing

Example test structure:

```python
def test_load_priority():
    db = LiveLoadDatabase()
    floor = Floor("test_floor")
    area = Area("test_area", [Point(0,0), Point(1,0), Point(1,1), Point(0,1)])
    
    # Test inheritance chain
    area.set_use_type("office_general", manual=True)
    load = floor.get_area_load("test_area", db)
    assert load.source == LoadSource.DIRECT
    assert load.value == 9.0
    
    # Test manual override
    area.set_manual_load(5.5)
    load = floor.get_area_load("test_area", db)
    assert load.source == LoadSource.DIRECT
    assert load.value == 5.5
```

## Future Enhancements

Planned features:
- Automatic balcony detection from geometry (optional)
- Area-weighted load calculations for mixed-use floors
- Load combination factors for code checks
- Export to structural analysis formats (SAP2000, ETABS direct)
- GUI for visual load assignment
- Multi-language support

## References

- Iranian National Building Code (INBC)
- Iran Standard 2800 (Seismic Design Code)
- ASCE 7 (American Standard for comparison)

## License

This module is part of the CivilTools project and follows the project's licensing terms.

## Support

For issues, questions, or contributions, refer to the main CivilTools documentation.
