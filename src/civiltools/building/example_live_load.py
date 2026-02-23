"""
نمونه استفاده از سیستم مدیریت بارهای زنده.

این فایل نشان می‌دهد:
- ساختن پروژه با چند طبقه
- اختصاص کاربری‌های مختلف به کف‌ها
- دریافت بارهای زنده با منبع
- چاپ گزارش
"""

from pathlib import Path
from civiltools.building.live_load_manager import (
    LiveLoadDatabase,
    Project,
    Floor,
    Area,
    Point,
)


def example_residential_and_commercial():
    """
    مثال: پروژه مختلط مسکونی-تجاری
    
    - طبقه همکف: کاربری تجاری
    - طبقه اول: کاربری مسکونی
    """
    print("=" * 80)
    print("مثال ۱: پروژه مختلط مسکونی-تجاری")
    print("=" * 80)

    # اولیه‌سازی دیتابیس
    db = LiveLoadDatabase()

    # ساختن پروژه
    project = Project(
        project_id="proj_001",
        project_name="ساختمان مختلط"
    )

    # ======== طبقه همکف (کاربری تجاری) ========
    ground_floor = Floor(
        floor_id="ground",
        floor_name="طبقه همکف",
        default_use="commercial"
    )

    # اضافه کردن کف‌ها
    area1 = Area(
        area_id="g_area1",
        geometry=[Point(0, 0), Point(5, 0), Point(5, 3), Point(0, 3)],
        use_type=None  # ارث‌بری از طبقه
    )
    ground_floor.add_area(area1)

    # یک فروشگاه خاص با بار بیشتر
    area2 = Area(
        area_id="g_shop",
        geometry=[Point(5, 0), Point(10, 0), Point(10, 3), Point(5, 3)],
        use_type="commercial_storage"  # کاربری خاص
    )
    ground_floor.add_area(area2)

    # راهرو
    area3 = Area(
        area_id="g_corridor",
        geometry=[Point(0, 3), Point(10, 3), Point(10, 4), Point(0, 4)],
        use_type="corridor"
    )
    ground_floor.add_area(area3)

    project.add_floor(ground_floor)

    # ======== طبقه اول (کاربری مسکونی) ========
    first_floor = Floor(
        floor_id="first",
        floor_name="طبقه اول",
        default_use="residential"
    )

    # اتاق نشیمن
    area4 = Area(
        area_id="1_living",
        geometry=[Point(0, 0), Point(6, 0), Point(6, 4), Point(0, 4)],
        use_type=None  # ارث‌بری از طبقه
    )
    first_floor.add_area(area4)

    # اتاق خواب
    area5 = Area(
        area_id="1_bedroom",
        geometry=[Point(6, 0), Point(10, 0), Point(10, 4), Point(6, 4)],
        use_type=None  # ارث‌بری از طبقه
    )
    first_floor.add_area(area5)

    # بالکن
    area6 = Area(
        area_id="1_balcony",
        geometry=[Point(6, 4), Point(10, 4), Point(10, 5), Point(6, 5)],
        use_type="residential_balcony"
    )
    first_floor.add_area(area6)

    project.add_floor(first_floor)

    # ======== چاپ گزارش ========
    print(f"\nپروژه: {project.project_name}")
    print(f"شناسه: {project.project_id}\n")

    for floor_id, floor in project.floors.items():
        print(f"\n{'─' * 70}")
        print(f"طبقه: {floor.floor_name} (ID: {floor.floor_id})")
        print(f"کاربری پیش‌فرض: {db.get_name(floor.default_use) if floor.default_use else 'ندارد'}")
        print(f"{'─' * 70}")

        for area_id, area in floor.areas.items():
            load_info = floor.get_area_load(area_id, db)
            print(f"\n  کف: {area_id}")
            print(f"    کاربری: {db.get_name(area.use_type) if area.use_type else '(ارث‌بری)'}")
            print(f"    بار زنده: {load_info.value:.2f} kN/m²")
            print(f"    منبع: {load_info.source.value}")
            print(f"    توضیح: {load_info.notes}")

    # ======== بررسی مغایرت‌ها ========
    print(f"\n\n{'=' * 70}")
    print("بررسی مغایرت‌های پروژه")
    print(f"{'=' * 70}")
    warnings = project.validate_all(db)
    if warnings:
        for floor_id, floor_warnings in warnings.items():
            print(f"\nطبقه {floor_id}:")
            for warning in floor_warnings:
                print(f"  ⚠ {warning}")
    else:
        print("✓ هیچ مغایرتی یافت نشد")


def example_with_manual_loads():
    """
    مثال ۲: استفاده از تعیین دستی بار
    """
    print("\n\n" + "=" * 80)
    print("مثال ۲: تعیین دستی بار")
    print("=" * 80)

    db = LiveLoadDatabase()

    project = Project("proj_002", "پروژه با بارهای دستی")

    floor = Floor("floor1", "طبقه ۱")

    # کف عادی
    area1 = Area(
        area_id="area1",
        geometry=[Point(0, 0), Point(5, 0), Point(5, 5), Point(0, 5)],
        use_type="residential"
    )
    floor.add_area(area1)

    # کف با بار دستی خاص
    area2 = Area(
        area_id="area2",
        geometry=[Point(5, 0), Point(10, 0), Point(10, 5), Point(5, 5)],
    )
    area2.set_manual_load(3.5)  # بار دستی
    floor.add_area(area2)

    project.add_floor(floor)

    print(f"\nپروژه: {project.project_name}\n")
    print("جدول بارهای زنده:")
    print(f"{'کف':<15} {'کاربری':<20} {'بار (kN/m²)':<15} {'منبع':<20}")
    print("─" * 70)

    for area_id, area in floor.areas.items():
        load_info = floor.get_area_load(area_id, db)
        use_name = db.get_name(area.use_type) if area.use_type else "دستی"
        print(f"{area_id:<15} {use_name:<20} {load_info.value:<15.2f} {load_info.source.value:<20}")


def example_list_all_use_types():
    """
    مثال ۳: نمایش تمام انواع کاربری موجود
    """
    print("\n\n" + "=" * 80)
    print("مثال ۳: دیتابیس انواع کاربری")
    print("=" * 80)

    db = LiveLoadDatabase()

    print(f"\nتعداد انواع کاربری: {len(db.list_use_types())}\n")
    print(f"{'شناسه':<25} {'نام':<20} {'بار (kN/m²)':<15} {'توضیح':<40}")
    print("─" * 100)

    for use_id in sorted(db.list_use_types()):
        load = db.get_load(use_id)
        name = db.get_name(use_id)
        description = db.get_description(use_id)
        print(f"{use_id:<25} {name:<20} {load:<15.2f} {description:<40}")

    print(f"\nبار پیش‌فرض کلی: {db.get_default_load()} kN/m²")


if __name__ == "__main__":
    # اجرای مثال‌ها
    example_residential_and_commercial()
    example_with_manual_loads()
    example_list_all_use_types()

    print("\n" + "=" * 80)
    print("پایان مثال‌ها")
    print("=" * 80)
