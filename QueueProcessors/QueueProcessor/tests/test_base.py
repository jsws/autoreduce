import unittest

from QueueProcessors.QueueProcessor.base import *
from QueueProcessors.QueueProcessor.settings import MYSQL


class TestBase(unittest.TestCase):

    def test_connection_string(self):
        expected_con_string = 'mysql+mysqldb://' + MYSQL['USER'] + ':' + MYSQL['PASSWD'] + \
                              '@' + MYSQL['HOST'] + '/' + MYSQL['DB']
        actual_con_string = connect_string
        self.assertEqual(expected_con_string, actual_con_string)

    def test_session(self):
        """
        Test that committing works - if so, we can be happy that the database connection is alive
        """
        print(session.query("SELECT 1"))



