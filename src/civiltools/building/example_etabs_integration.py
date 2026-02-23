"""
Integration Example: ETABS Live Load Management

This example demonstrates how to:
1. Connect to an active ETABS model
2. Read story information directly from ETABS
3. Create a live load management project
4. Assign use types to floors
5. Calculate and display live loads for all floors
6. Generate a comprehensive report

Prerequisites:
- ETABS must be running with a model loaded
- The civiltools package must be properly installed with etabs_api as a dependency
"""

from civiltools.etabs.connection import EtabsConnection
from civiltools.building.etabs_story_reader import ETABSStoryReader, ETABSProjectBuilder
from civiltools.building.live_load_manager import LiveLoadDatabase


def example_1_basic_etabs_connection():
    """
    Example 1: Connect to ETABS and read story information directly.
    
    This is the simplest example showing basic story reading.
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Basic ETABS Connection and Story Reading")
    print("=" * 80)
    
    try:
        # Step 1: Connect to ETABS
        etabs_conn = EtabsConnection()
        if not etabs_conn.connect():
            print(f"Error: {etabs_conn.last_error}")
            return
        
        print(f"✓ Connected to ETABS model: {etabs_conn.model_path}\n")
        
        # Step 2: Create a story reader
        reader = ETABSStoryReader(etabs_conn.etabs)
        
        # Step 3: Print story summary
        reader.print_stories_summary()
        
        # Step 4: Display detailed story information
        print("\nDetailed Story Information:")
        print("-" * 80)
        
        stories_info = reader.get_all_stories_info()
        for story_name in reader.get_story_names(reverse=True, include_base=False):
            info = stories_info[story_name]
            print(f"\n{story_name}:")
            print(f"  Elevation: {info['elevation']:.2f}")
            print(f"  Height from previous: {info['height']:.2f}")
            print(f"  Structural elements: {info['number_of_points']} points, "
                  f"{info['number_of_areas']} areas")
            print(f"  Bounding box: {info['bounding_box']}")
        
        # Step 5: Validate stories
        warnings = reader.validate_stories()
        if warnings:
            print("\n⚠ Validation Warnings:")
            for warning in warnings:
                print(f"  - {warning}")
        else:
            print("\n✓ Story validation passed - no issues found")
        
        # Disconnect
        etabs_conn.disconnect()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


def example_2_create_project_with_use_types():
    """
    Example 2: Create a complete live load project from ETABS with use type assignments.
    
    This example shows:
    - Reading all stories
    - Assigning use types to each floor
    - Creating a complete project
    - Calculating live loads for each floor
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Create Live Load Project with Use Type Assignments")
    print("=" * 80)
    
    try:
        # Connect to ETABS
        etabs_conn = EtabsConnection()
        if not etabs_conn.connect():
            print(f"Error: {etabs_conn.last_error}")
            return
        
        print(f"✓ Connected to ETABS\n")
        
        # Create a project builder
        builder = ETABSProjectBuilder(etabs_conn.etabs)
        
        # Configure the project
        project = (builder
            .set_project_info(
                project_id="bldg_001",
                project_name="Multi-Story Office Building"
            )
            .apply_default_use_to_all("office_general")
            .build())
        
        print(f"✓ Project created: {project.project_name}\n")
        
        # Display project information
        print("=" * 80)
        print("PROJECT STRUCTURE")
        print("=" * 80)
        
        database = LiveLoadDatabase()
        
        total_area_count = 0
        for floor_id in sorted(project.floors.keys()):
            floor = project.floors[floor_id]
            print(f"\n{floor.floor_name} ({floor_id})")
            print(f"  Default use type: {database.get_name(floor.default_use) if floor.default_use else 'None'}")
            print(f"  Number of areas: {len(floor.areas)}")
            total_area_count += len(floor.areas)
            
            # Show live load for this floor (based on default use)
            if floor.areas:
                # Get load from first area (they'll all be the same if using default)
                first_area_id = list(floor.areas.keys())[0]
                load_info = floor.get_area_load(first_area_id, database)
                print(f"  Live load: {load_info.value:.2f} kN/m² ({load_info.source.value})")
        
        print(f"\n{'=' * 80}")
        print(f"Total areas: {total_area_count}")
        print(f"{'=' * 80}\n")
        
        # Disconnect
        etabs_conn.disconnect()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


def example_3_mixed_use_types():
    """
    Example 3: Assign different use types to different floors.
    
    This example demonstrates:
    - Using ETABSProjectBuilder with specific floor assignments
    - Mixed-use buildings
    - Complex load patterns
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Mixed-Use Building with Different Floor Types")
    print("=" * 80)
    
    try:
        # Connect to ETABS
        etabs_conn = EtabsConnection()
        if not etabs_conn.connect():
            print(f"Error: {etabs_conn.last_error}")
            return
        
        print(f"✓ Connected to ETABS\n")
        
        # Create builder
        builder = ETABSProjectBuilder(etabs_conn.etabs)
        reader = builder.reader
        
        # Set project info
        builder.set_project_info("mixed_use_001", "Mixed-Use Commercial/Residential")
        
        # Get all story names
        story_names = reader.get_story_names(reverse=True, include_base=False)
        
        print(f"Found {len(story_names)} stories in model:")
        for i, story in enumerate(story_names):
            print(f"  {i+1}. {story}")
        print()
        
        # Assign use types based on floor level
        # Typical pattern: retail on ground, offices on middle, residential on top
        if len(story_names) >= 3:
            builder.apply_use_to_floor(story_names[-1], "retail_small_ground")  # Lowest floor
            
            # Middle floors for offices
            for story in story_names[1:-1]:
                builder.apply_use_to_floor(story, "office_general")
            
            # Top floors for residential
            builder.apply_use_to_floor(story_names[0], "residential_rooms")  # Top floor
        else:
            # If fewer floors, use default
            builder.apply_default_use_to_all("office_general")
        
        # Build the project
        project = builder.build()
        
        # Print configuration
        print("Floor Use Type Assignments:")
        print("-" * 80)
        builder.print_summary()
        
        # Generate detailed report
        print("\n" + "=" * 80)
        print("LIVE LOAD CALCULATION REPORT")
        print("=" * 80)
        
        database = LiveLoadDatabase()
        
        print(f"\n{'Floor':<20} {'Use Type':<30} {'Load (kN/m²)':<15} {'Source':<20}")
        print("-" * 85)
        
        for floor_id in sorted(project.floors.keys()):
            floor = project.floors[floor_id]
            
            # Calculate representative load for this floor
            if floor.areas:
                first_area_id = list(floor.areas.keys())[0]
                load_info = floor.get_area_load(first_area_id, database)
                use_name = database.get_name(load_info.use_type) if load_info.use_type else "Default"
            else:
                use_name = "No areas"
                load_info = None
            
            if load_info:
                print(
                    f"{floor_id:<20} "
                    f"{use_name:<30} "
                    f"{load_info.value:<15.2f} "
                    f"{load_info.source.value:<20}"
                )
            else:
                print(f"{floor_id:<20} {use_name:<30}")
        
        print("=" * 85)
        
        # Disconnect
        etabs_conn.disconnect()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


def example_4_database_reference():
    """
    Example 4: Explore the live load database.
    
    This example shows all available use types and their properties.
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Live Load Database Reference")
    print("=" * 80)
    print()
    
    database = LiveLoadDatabase()
    
    # Display all use types
    print("Available Use Types in Database:")
    print("-" * 100)
    
    use_types = database.list_use_types_with_names()
    
    print(f"{'ID':<30} {'Name':<30} {'Load (kN/m²)':<15} {'Description':<50}")
    print("-" * 100)
    
    for use_id in sorted(use_types.keys()):
        load = database.get_load(use_id)
        name = database.get_name(use_id)
        description = database.get_description(use_id)[:47]  # Truncate for display
        
        print(
            f"{use_id:<30} "
            f"{name:<30} "
            f"{load:<15.2f} "
            f"{description:<50}"
        )
    
    print("-" * 100)
    print(f"Total: {len(use_types)} use types available")
    print(f"Default load: {database.get_default_load()} kN/m²\n")


def example_5_validation_and_reporting():
    """
    Example 5: Validate project configuration and generate reports.
    
    This example demonstrates:
    - Story validation
    - Project validation
    - Detailed reporting
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Project Validation and Reporting")
    print("=" * 80)
    
    try:
        # Connect to ETABS
        etabs_conn = EtabsConnection()
        if not etabs_conn.connect():
            print(f"Error: {etabs_conn.last_error}")
            return
        
        print(f"✓ Connected to ETABS\n")
        
        # Create reader and validate stories
        reader = ETABSStoryReader(etabs_conn.etabs)
        
        print("Story Validation Results:")
        print("-" * 80)
        warnings = reader.validate_stories()
        
        if warnings:
            print("⚠ WARNINGS FOUND:")
            for i, warning in enumerate(warnings, 1):
                print(f"  {i}. {warning}")
        else:
            print("✓ All stories validated successfully")
        
        print()
        
        # Create and validate project
        project = reader.create_project("test_proj", "Validation Test")
        
        print("Project Validation Results:")
        print("-" * 80)
        
        database = LiveLoadDatabase()
        proj_warnings = project.validate_all(database)
        
        if proj_warnings:
            print("⚠ ISSUES FOUND:")
            for floor_id, issues in proj_warnings.items():
                print(f"\n  {floor_id}:")
                for issue in issues:
                    print(f"    - {issue}")
        else:
            print("✓ Project validation passed")
        
        # Generate summary
        print("\n" + "=" * 80)
        print("PROJECT SUMMARY")
        print("=" * 80)
        
        stories_info = reader.get_all_stories_info()
        
        total_points = sum(info['number_of_points'] for info in stories_info.values())
        total_areas = sum(info['number_of_areas'] for info in stories_info.values())
        
        print(f"Total stories: {len(project.floors)}")
        print(f"Total structural points: {total_points}")
        print(f"Total areas/elements: {total_areas}")
        print()
        
        # Disconnect
        etabs_conn.disconnect()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("ETABS LIVE LOAD MANAGEMENT - INTEGRATION EXAMPLES")
    print("=" * 80)
    
    # Run examples
    # Uncomment the examples you want to run:
    
    example_4_database_reference()  # Safe to run without ETABS
    
    # Requires ETABS connection:
    # example_1_basic_etabs_connection()
    # example_2_create_project_with_use_types()
    # example_3_mixed_use_types()
    # example_5_validation_and_reporting()
    
    print("\n" + "=" * 80)
    print("Examples completed")
    print("=" * 80)
