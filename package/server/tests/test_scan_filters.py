import os
import tempfile
import unittest

from app.service.tasks.scan import scan_directory_recursive


class ScanFiltersTest(unittest.TestCase):
    def test_scan_skips_synology_eadir_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            real_photo = os.path.join(tmp, "IMG_0001.JPG")
            os.makedirs(os.path.join(tmp, "@eaDir", "IMG_0001.JPG"))
            metadata_thumb = os.path.join(tmp, "@eaDir", "IMG_0001.JPG", "SYNOPHOTO_THUMB_M.jpg")

            open(real_photo, "wb").close()
            open(metadata_thumb, "wb").close()

            found = scan_directory_recursive(tmp, {".jpg", ".jpeg"})

        self.assertEqual(found, {real_photo})


if __name__ == "__main__":
    unittest.main()
