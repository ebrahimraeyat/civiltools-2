"""
Live Load Management Module

مدیریت بارهای زنده در پروژه‌های تحلیل سازه‌ای.
سیستم دارای قابلیت ارث‌بری بار، محاسبه خودکار برای بالکن‌ها، و پیگیری منبع بار است.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional
from enum import Enum


class LoadSource(str, Enum):
    """منبع تعیین بار."""
    DIRECT = "direct"  # تعیین مستقیم برای کف
    INHERITED_FLOOR = "inherited_floor"  # ارث‌بری از کاربری پیش‌فرض طبقه
    INHERITED_PROJECT = "inherited_project"  # ارث‌بری از پروژه
    CALCULATED = "calculated"  # محاسبه شده (مثلاً برای بالکن)


@dataclass
class LoadInfo:
    """اطلاعات بار زنده شامل مقدار و منبع."""
    value: float  # بار زنده (kN/m²)
    source: LoadSource
    use_type: Optional[str] = None
    notes: str = ""

    def __str__(self) -> str:
        return f"{self.value:.2f} kN/m² ({self.source.value})"


@dataclass
class Point:
    """نقطه دوبعدی برای تعریف هندسه."""
    x: float
    y: float


@dataclass
class Area:
    """کف یا فضای درون طبقه."""
    
    area_id: str
    geometry: list[Point]  # لیست نقاط چندضلعی
    use_type: Optional[str] = None
    _manual_override: Optional[float] = None

    @property
    def load_source(self) -> LoadSource:
        """منبع تعیین بار این کف."""
        if self._manual_override is not None:
            return LoadSource.DIRECT
        elif self.use_type is not None:
            return LoadSource.DIRECT
        else:
            return LoadSource.INHERITED_FLOOR

    @property
    def current_use_type(self) -> Optional[str]:
        """کاربری فعلی کف (مستقیم یا ارث‌بری)."""
        return self.use_type

    def set_use_type(self, use_type: str, manual: bool = True) -> None:
        """
        تنظیم نوع کاربری کف.
        
        Args:
            use_type: نوع کاربری جدید
            manual: اگر True، به عنوان تعیین مستقیم ثبت شود
        """
        self.use_type = use_type if manual else None

    def set_manual_load(self, load: float) -> None:
        """تنظیم مستقیم مقدار بار بدون توجه به کاربری."""
        self._manual_override = load

    def clear_manual_load(self) -> None:
        """حذف تعیین دستی بار."""
        self._manual_override = None

    def __repr__(self) -> str:
        return f"Area(id={self.area_id}, use={self.use_type}, source={self.load_source.value})"


@dataclass
class Floor:
    """طبقه شامل مجموعه‌ای از کف‌ها."""
    
    floor_id: str
    floor_name: str = ""
    default_use: Optional[str] = None  # کاربری پیش‌فرض کل طبقه
    areas: dict[str, Area] = field(default_factory=dict)

    def add_area(self, area: Area) -> None:
        """اضافه کردن کف جدید به طبقه."""
        self.areas[area.area_id] = area

    def apply_default_use(self, use_type: str) -> None:
        """
        اعمال کاربری پیش‌فرض به تمام کف‌های بدون کاربری مشخص.
        
        Args:
            use_type: کاربری پیش‌فرض جدید
        """
        self.default_use = use_type
        for area in self.areas.values():
            if area.use_type is None and area._manual_override is None:
                pass  # ارث‌بری خودکار در get_area_load

    def get_area_load(
        self,
        area_id: str,
        database: LiveLoadDatabase,
    ) -> LoadInfo:
        """
        بدست آوردن بار زنده کف با اولویت معیار.
        
        اولویت:
        1. تعیین دستی (_manual_override)
        2. کاربری مشخص کف (air_use_type)
        3. کاربری پیش‌فرض طبقه (floor.default_use)
        4. مقدار پیش‌فرض کلی پروژه
        
        Args:
            area_id: شناسه کف
            database: دیتابیس بارهای زنده
            
        Returns:
            اطلاعات بار (مقدار + منبع)
        """
        if area_id not in self.areas:
            raise ValueError(f"Area {area_id} not found in floor {self.floor_id}")

        area = self.areas[area_id]

        # 1. تعیین دستی
        if area._manual_override is not None:
            return LoadInfo(
                value=area._manual_override,
                source=LoadSource.DIRECT,
                use_type=None,
                notes="تعیین دستی",
            )

        # 2. کاربری مشخص کف
        if area.use_type is not None:
            load = database.get_load(area.use_type)
            return LoadInfo(
                value=load,
                source=LoadSource.DIRECT,
                use_type=area.use_type,
                notes=f"کاربری مستقیم: {database.get_description(area.use_type)}",
            )

        # 3. کاربری پیش‌فرض طبقه
        if self.default_use is not None:
            load = database.get_load(self.default_use)
            return LoadInfo(
                value=load,
                source=LoadSource.INHERITED_FLOOR,
                use_type=self.default_use,
                notes=f"ارث‌بری از طبقه: {database.get_description(self.default_use)}",
            )

        # 4. مقدار پیش‌فرض کلی
        default_load = database.get_default_load()
        return LoadInfo(
            value=default_load,
            source=LoadSource.INHERITED_PROJECT,
            use_type=None,
            notes="مقدار پیش‌فرض پروژه",
        )

    def validate(self) -> list[str]:
        """
        بررسی مغایرت‌های احتمالی در طبقه.
        
        Returns:
            لیست پیام‌های هشدار
        """
        warnings = []
        if not self.areas:
            warnings.append(f"Floor {self.floor_id} has no areas")
        if self.default_use is None and not all(a.use_type for a in self.areas.values()):
            warnings.append(
                f"Floor {self.floor_id} has no default use and some areas have no assigned type"
            )
        return warnings

    def __repr__(self) -> str:
        return f"Floor(id={self.floor_id}, name={self.floor_name}, areas={len(self.areas)})"


@dataclass
class Project:
    """پروژه شامل مجموعه‌ای از طبقات."""
    
    project_id: str
    project_name: str = ""
    floors: dict[str, Floor] = field(default_factory=dict)

    def add_floor(self, floor: Floor) -> None:
        """اضافه کردن طبقه جدید به پروژه."""
        self.floors[floor.floor_id] = floor

    def validate_all(self, database: LiveLoadDatabase) -> dict[str, list[str]]:
        """
        بررسی کل پروژه.
        
        Returns:
            دیکشنری هشدارها برای هر طبقه
        """
        warnings = {}
        for floor_id, floor in self.floors.items():
            floor_warnings = floor.validate()
            if floor_warnings:
                warnings[floor_id] = floor_warnings
        return warnings

    def __repr__(self) -> str:
        return f"Project(id={self.project_id}, name={self.project_name}, floors={len(self.floors)})"


class LiveLoadDatabase:
    """
    دیتابیس بارهای زنده استاندارد.
    
    بارگذاری از فایل JSON و ارائه رابط کاری برای دریافت بارهای مختلف کاربری‌ها.
    """

    def __init__(self, data_file: Optional[Path] = None):
        """
        اولیه‌سازی دیتابیس.
        
        Args:
            data_file: مسیر فایل JSON (اختیاری، از مسیر پیش‌فرض استفاده شود)
        """
        if data_file is None:
            # مسیر پیش‌فرض: هم‌جوار این فایل
            data_file = Path(__file__).parent / "live_load_data.json"

        self.data_file = data_file
        self._data = self._load_data()

    def _load_data(self) -> dict:
        """بارگذاری فایل JSON."""
        if not self.data_file.exists():
            raise FileNotFoundError(f"Live load data file not found: {self.data_file}")

        with open(self.data_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_load(self, use_type: str) -> float:
        """
        Get distributed live load for a use type.
        
        Args:
            use_type: Type of use/occupancy
            
        Returns:
            Distributed live load value (kN/m²)
            
        Raises:
            ValueError: if use type is not found
        """
        if use_type not in self._data["uses"]:
            raise ValueError(
                f"Unknown use type: {use_type}. "
                f"Available types: {', '.join(self._data['uses'].keys())}"
            )
        load = self._data["uses"][use_type]["default_load"]
        if load is None:
            raise ValueError(
                f"Use type '{use_type}' has no default distributed load defined"
            )
        return load

    def get_concentrated_load(self, use_type: str) -> float | None:
        """
        Get concentrated/point load for a use type.
        
        Args:
            use_type: Type of use/occupancy
            
        Returns:
            Concentrated load value (kN) or None if not applicable
            
        Raises:
            ValueError: if use type is not found
        """
        if use_type not in self._data["uses"]:
            raise ValueError(f"Unknown use type: {use_type}")
        return self._data["uses"][use_type].get("concentrated_load")

    def get_description(self, use_type: str) -> str:
        """
        دریافت توضیح برای نوع کاربری.
        
        Args:
            use_type: نوع کاربری
            
        Returns:
            توضیح نوع کاربری
        """
        if use_type not in self._data["uses"]:
            return "نامعلوم"
        return self._data["uses"][use_type]["description"]

    def get_name(self, use_type: str) -> str:
        """
        دریافت نام نمایشی نوع کاربری.
        
        Args:
            use_type: نوع کاربری
            
        Returns:
            نام نمایشی
        """
        if use_type not in self._data["uses"]:
            return use_type
        return self._data["uses"][use_type]["name"]

    def get_default_load(self) -> float:
        """مقدار بار پیش‌فرض کلی پروژه."""
        return self._data["default"]["load"]

    def list_use_types(self) -> list[str]:
        """لیست تمام انواع کاربری موجود."""
        return list(self._data["uses"].keys())

    def list_use_types_with_names(self) -> dict[str, str]:
        """لیست کاربری‌ها با نام‌های نمایشی."""
        return {
            use_id: self._data["uses"][use_id]["name"]
            for use_id in self._data["uses"].keys()
        }
