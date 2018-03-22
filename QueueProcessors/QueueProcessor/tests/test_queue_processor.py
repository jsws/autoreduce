import unittest
from QueueProcessors.QueueProcessor.queue_processor import Listener


class TestQueueProcessorListener(unittest.TestCase):

    def test_create_listener(self):
        listener = Listener()
        self.assertIsNotNone(listener)