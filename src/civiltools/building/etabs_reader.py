"""
ETABS Story Reader Integration

Reads story data from an active ETABS model and converts it into the
Pydantic-based Floor models for live load management.
"""

from typing import Optional, List, Tuple, Dict, Any
from pathlib import Path

from civiltools.building.models import Project, Floor
from civiltools.building.database import LiveLoadDatabase


class ETABSStoryReader:
    """
    Reads story/floor information from an active ETABS model.
    
    This class interfaces with the ETABS COM API through the etabs_api package
    to extract all story definitions and organize them into Floor objects that
    can be used with the live load management system.
    """

    def __init__(self, etabs_obj: Any, database: Optional[LiveLoadDatabase] = None):
        """
        Initialize the ETABS story reader.
        
        Args:
            etabs_obj: An active EtabsModel instance (from etabs_api.etabs_obj.EtabsModel)
            database: Optional LiveLoadDatabase for reference and validation
        """
        self.etabs = etabs_obj
        self.story_obj = etabs_obj.story  # Assumes etabs_obj has a .story attribute
        self.database = database or LiveLoadDatabase()

    def get_sorted_stories(
        self,
        reverse: bool = True,
        include_base: bool = False,
        unit: Optional[str] = None,
    ) -> List[Tuple[str, float]]:
        """
        Get sorted stories from ETABS model.
        
        Uses the story.get_sorted_story_and_levels() method to retrieve
        story names and their elevations, sorted by elevation.
        
        Args:
            reverse: If True, sort from top to bottom (default). 
                    If False, sort from bottom to top.
            include_base: If True, include base/foundation level in results.
            unit: Target unit for elevations (e.g., 'm', 'cm'). 
                 If None, uses current ETABS unit.
        
        Returns:
            List of tuples (story_name, elevation) sorted by elevation level.
        """
        return self.story_obj.get_sorted_story_and_levels(
            reverse=reverse,
            include_base=include_base,
            unit=unit,
        )

    def get_story_names(self, reverse: bool = True, include_base: bool = False) -> List[str]:
        """
        Get list of story names.
        
        Args:
            reverse: If True, sort from top to bottom.
            include_base: If True, include base/foundation level.
        
        Returns:
            List of story names in sorted order.
        """
        return self.story_obj.get_sorted_story_name(
            reverse=reverse,
            include_base=include_base,
        )

    def get_story_elevation(self, story_name: str, unit: Optional[str] = None) -> float:
        """
        Get the elevation of a specific story.
        
        Args:
            story_name: Name of the story in ETABS.
            unit: Optional target unit. If specified, converts elevation to this unit.
        
        Returns:
            Elevation value as float.
        """
        return self.story_obj.get_elevation(story_name)

    def get_all_stories_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get comprehensive information about all stories in the model.
        
        Returns:
            Dictionary mapping story names to their information:
            {
                'story_name': {
                    'elevation': float,
                    'height': float (from previous story),
                    'number_of_points': int,
                    'number_of_areas': int,
                    'bounding_box': (x_min, y_min, x_max, y_max),
                }
            }
        """
        stories_info = {}
        stories_with_levels = self.get_sorted_stories(reverse=True, include_base=True)
        
        for i, (story_name, elevation) in enumerate(stories_with_levels):
            # Calculate story height
            height = 0.0
            if i < len(stories_with_levels) - 1:
                prev_elevation = stories_with_levels[i + 1][1]
                height = elevation - prev_elevation
            
            # Get number of points and areas on this story
            try:
                points = self.etabs.SapModel.PointObj.GetNameListOnStory(story_name)[1]
                num_points = len(points) if points else 0
            except Exception:
                num_points = 0
            
            try:
                areas = self.etabs.SapModel.AreaObj.GetNameListOnStory(story_name)[1]
                num_areas = len(areas) if areas else 0
            except Exception:
                num_areas = 0
            
            # Get bounding box
            try:
                bbox = self.story_obj.get_story_boundbox(story_name)
            except Exception:
                bbox = (0, 0, 0, 0)
            
            stories_info[story_name] = {
                'elevation': elevation,
                'height': height,
                'number_of_points': num_points,
                'number_of_areas': num_areas,
                'bounding_box': bbox,
            }
        
        return stories_info

    def create_floors_from_stories(self) -> Dict[str, Floor]:
        """
        Create Floor objects from ETABS stories.
        
        Each story in ETABS becomes a Floor object. By default, no use type
        or area-specific loads are set; these must be assigned by the user.
        
        Returns:
            Dictionary mapping story names to Floor objects.
        """
        floors = {}
        stories_info = self.get_all_stories_info()
        
        for story_name, info in stories_info.items():
            floor = Floor(
                floor_id=story_name,
                floor_name=story_name,
                elevation=info['elevation'],
                height=info['height'],
                default_use=None,  # User must assign
            )
            floors[story_name] = floor
        
        return floors

    def create_project(
        self,
        project_id: str,
        project_name: str = "",
        default_floor_use: Optional[str] = None,
    ) -> Project:
        """
        Create a Project with all stories from the ETABS model.
        
        Args:
            project_id: Unique identifier for the project.
            project_name: Optional display name for the project.
                         If empty, uses ETABS model filename.
            default_floor_use: Optional default use type to apply to all floors.
        
        Returns:
            A Project object populated with Floor objects from ETABS stories.
        """
        if not project_name:
            try:
                project_name = Path(self.etabs.model_path).stem
            except Exception:
                project_name = project_id
        
        project = Project(
            project_id=project_id,
            project_name=project_name,
        )
        
        # Add all floors
        floors = self.create_floors_from_stories()
        for floor in floors.values():
            if default_floor_use:
                floor.apply_default_use(default_floor_use)
            project.add_floor(floor)
        
        return project

    def print_stories_summary(self) -> None:
        """
        Print a formatted summary of all stories in the model.
        
        Useful for quick inspection of the model structure.
        """
        print("\n" + "=" * 80)
        print("ETABS Model Stories Summary")
        print("=" * 80)
        
        try:
            model_path = self.etabs.model_path
            print(f"Model: {model_path}")
        except Exception:
            print("Model: (unknown)")
        
        print()
        
        stories_info = self.get_all_stories_info()
        
        print(f"{'Story':<20} {'Elevation':<15} {'Height':<15} {'Points':<10} {'Areas':<10}")
        print("-" * 80)
        
        for story_name in self.get_story_names(reverse=True, include_base=True):
            info = stories_info[story_name]
            print(
                f"{story_name:<20} "
                f"{info['elevation']:<15.2f} "
                f"{info['height']:<15.2f} "
                f"{info['number_of_points']:<10} "
                f"{info['number_of_areas']:<10}"
            )
        
        print("=" * 80)
        print()

    def validate_stories(self) -> List[str]:
        """
        Validate story configuration and return warnings.
        
        Returns:
            List of warning messages (empty if all OK).
        """
        warnings = []
        stories = self.get_story_names(reverse=True, include_base=False)
        
        if not stories:
            warnings.append("No stories found in model (excluding base).")
            return warnings
        
        stories_info = self.get_all_stories_info()
        
        # Check for inconsistent story heights
        heights = []
        for story in stories:
            height = stories_info[story]['height']
            if height > 0:
                heights.append(height)
        
        if heights:
            avg_height = sum(heights) / len(heights)
            for story in stories:
                height = stories_info[story]['height']
                if height > 0 and abs(height - avg_height) > avg_height * 0.2:
                    warnings.append(
                        f"Story '{story}' has unusual height: {height:.2f} "
                        f"(average: {avg_height:.2f})"
                    )
        
        # Check for stories with no structural elements
        for story in stories:
            info = stories_info[story]
            if info['number_of_points'] == 0 and info['number_of_areas'] == 0:
                warnings.append(f"Story '{story}' has no points or areas.")
        
        return warnings


class ETABSProjectBuilder:
    """
    High-level builder for creating live load projects from ETABS models.
    
    This class provides a fluent interface for:
    - Reading ETABS stories
    - Assigning use types to floors
    - Creating and configuring the live load project
    """

    def __init__(self, etabs_obj: Any):
        """
        Initialize the project builder.
        
        Args:
            etabs_obj: An active EtabsModel instance.
        """
        self.reader = ETABSStoryReader(etabs_obj)
        self.project_id = "project_001"
        self.project_name = ""
        self.floor_uses: Dict[str, str] = {}  # story_name -> use_type mapping
        self._project: Optional[Project] = None

    def set_project_info(self, project_id: str, project_name: str = "") -> 'ETABSProjectBuilder':
        """
        Set project identification information.
        
        Args:
            project_id: Unique project identifier.
            project_name: Display name for the project.
        
        Returns:
            Self for method chaining.
        """
        self.project_id = project_id
        self.project_name = project_name
        return self

    def apply_use_to_floor(self, story_name: str, use_type: str) -> 'ETABSProjectBuilder':
        """
        Assign a specific use type to a floor.
        
        Args:
            story_name: ETABS story name.
            use_type: Use type from live load database.
        
        Returns:
            Self for method chaining.
        """
        self.floor_uses[story_name] = use_type
        return self

    def apply_default_use_to_all(self, use_type: str) -> 'ETABSProjectBuilder':
        """
        Assign the same use type to all floors.
        
        Args:
            use_type: Use type from live load database.
        
        Returns:
            Self for method chaining.
        """
        story_names = self.reader.get_story_names(reverse=True, include_base=False)
        for story_name in story_names:
            self.floor_uses[story_name] = use_type
        return self

    def build(self) -> Project:
        """
        Build and return the final Project object.
        
        Returns:
            A fully configured Project ready for live load calculations.
        """
        self._project = self.reader.create_project(self.project_id, self.project_name)
        
        # Apply use types
        for story_name, use_type in self.floor_uses.items():
            if story_name in self._project.floors:
                self._project.floors[story_name].apply_default_use(use_type)
        
        return self._project

    def print_summary(self) -> None:
        """Print a summary of the configured project."""
        self.reader.print_stories_summary()
        
        print("Floor Use Type Assignments:")
        print("-" * 50)
        for story_name in self.reader.get_story_names(reverse=True, include_base=False):
            use_type = self.floor_uses.get(story_name, "(not assigned)")
            print(f"  {story_name:<20} -> {use_type}")
        print()
