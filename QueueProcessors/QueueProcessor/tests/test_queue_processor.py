import unittest

from QueueProcessors.QueueProcessor.queue_processor import Listener, logger

# Test data for header combinations
VALID_PRIORITIES = ['Low', 'Medium', 'High']
INVALID = ['invalid', 123, None, '']
VALID_QUEUE_DESTINATIONS = ['/queue/DataReady', '/queue/ReductionStarted', '/queue/ReductionComplete',
                            '/queue/ReductionError']
INVALID_QUEUE_DESTINATIONS = ['invalid', 123, None, '']


class TestQueueProcessorListener(unittest.TestCase):

    listener = None

    @classmethod
    def setUpClass(cls):
        open("test-output.log", "w").close()

    def setUp(self):
        self.listener = Listener(self)

    def test_create_listener(self):
        self.assertIsInstance(self.listener, Listener)

    def test_valid_on_message(self):
        """
        Test all the valid combinations of message properties do not raise exceptions
        Additionally, check the log to ensure they run as expected
        """
        for prop in VALID_PRIORITIES:
            for destination in VALID_QUEUE_DESTINATIONS:
                # ToDo: create Json generator function - need to check correct keys
                self.listener.on_message(_generate_header(destination, prop),
                                         _generate_json_msg("123", "TEST", "123", "1"))
                # ToDo: Test logger is expected output

    '''def test_invalid_on_message(self):
        for prop in VALID_PRIORITIES:
            for destination in INVALID_QUEUE_DESTINATIONS:
                self.listener.'''

    def send(self, destination=None, message=None, persistent=None, priority=None, delay=None):
        """Function to mock sending"""
        pass

    def tearDown(self):
        del self.listener


# ===========================Test helpers========================== #
def _generate_header(destination=None, priority=None):
    return {"destination": destination, "priority": priority}


def _generate_json_msg(run_number=None, instrument=None, rb_number=None, run_version=None):
    return '{"run_number": "' + run_number + '",'  \
           ' "instrument": "' + instrument + '",'  \
           ' "rb_number": "' + rb_number + '",'    \
           ' "run_version": "' + run_version + '",'\
           ' "data": "some_data"}'
