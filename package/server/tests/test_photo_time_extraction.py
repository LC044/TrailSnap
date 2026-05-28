from datetime import datetime
import unittest

from app.utils.exif import extract_datetime_from_path, parse_datetime_value
from app.utils.filename import extract_datetime_from_filename


class PhotoTimeExtractionTest(unittest.TestCase):
    def test_extract_date_only_from_filename(self):
        self.assertEqual(extract_datetime_from_filename("20250227").date(), datetime(2025, 2, 27).date())
        self.assertEqual(extract_datetime_from_filename("album 2024-3-28").date(), datetime(2024, 3, 28).date())

    def test_extract_date_from_dated_folder(self):
        path = "/app/Photos/20250227/DSC_1991.JPG"

        self.assertEqual(extract_datetime_from_path(path), datetime(2025, 2, 27))

    def test_extract_inherited_year_month_day_from_folder(self):
        path = "/app/Photos/2020.09.13罗文琪&文晶photo/9.15/jpg/1A5A8450z.jpg"

        self.assertEqual(extract_datetime_from_path(path), datetime(2020, 9, 15))

    def test_extract_short_year_folder_date(self):
        path = "/app/Photos/文晶写真照片/211004大唐芙蓉园（文女士）/DSC09505.JPG"

        self.assertEqual(extract_datetime_from_path(path), datetime(2021, 10, 4))

    def test_parse_exif_datetime_fallback_value(self):
        self.assertEqual(parse_datetime_value("2024:10:28 09:24:47"), datetime(2024, 10, 28, 9, 24, 47))


if __name__ == "__main__":
    unittest.main()
