import unittest

from app.db.models.task import TaskType
from app.service.task_worker import get_chunk_size


class TaskWorkerChunkingTest(unittest.TestCase):
    def test_face_recognition_uses_single_image_batches(self):
        self.assertEqual(get_chunk_size(TaskType.RECOGNIZE_FACE), 1)

    def test_classification_uses_small_batches(self):
        self.assertEqual(get_chunk_size(TaskType.CLASSIFY_IMAGE), 2)


if __name__ == "__main__":
    unittest.main()
