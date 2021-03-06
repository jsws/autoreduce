import sys, time, logging, os, datetime, json, shutil, getpass
from sets import Set
from mock import patch
from xml.sax import SAXParseException

from django.test import TestCase, TransactionTestCase 
from django.utils import timezone
from autoreduce_webapp.settings import LOG_FILE, LOG_LEVEL, ACTIVEMQ, BASE_DIR, TEST_REDUCTION_DIRECTORY, ICAT, UOWS_URL, UOWS_LOGIN_URL
logging.basicConfig(filename=LOG_FILE.replace('.log', '.test.log'),level=LOG_LEVEL, format=u'%(message)s',)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
sys.path.insert(0, BASE_DIR)

from icat.exception import ICATSessionError
from suds.client import Client as suds_client

with patch('autoreduce_webapp.settings.REDUCTION_DIRECTORY', TEST_REDUCTION_DIRECTORY):
    from reduction_viewer.models import ReductionRun, Instrument, ReductionLocation, Status, Experiment, DataLocation
    from reduction_viewer.utils import StatusUtils
    from reduction_variables.models import InstrumentVariable, RunVariable

    from autoreduce_webapp.icat_communication import ICATCommunication
    from autoreduce_webapp.uows_client import UOWSClient
    from autoreduce_webapp.daemon import Daemon
    from autoreduce_webapp.queue_processor_daemon import QueueProcessorDaemon
    from autoreduce_webapp.queue_processor import Client, Listener

from utils import copyScripts, removeScripts

rb_number = 2

       
            
class QueueProcessorTestCase(TransactionTestCase):
    '''
        Insert any data that is needed for tests
    '''
    def setUp(self):
        instrument1, created1 = Instrument.objects.get_or_create(name="ExistingTestInstrument1")
        instrument2, created2 = Instrument.objects.get_or_create(name="InactiveInstrument", is_active=False)
        self.save_dummy_reduce_script("InactiveInstrument")
        self.save_dummy_reduce_script("ExistingTestInstrument1")

    '''
        Remove InactiveInstrument dummy script
    '''
    def tearDown(self):
        pass

    @classmethod
    def setUpClass(cls):
        cls._client = Client(ACTIVEMQ['broker'], ACTIVEMQ['username'], ACTIVEMQ['password'], ACTIVEMQ['topics'], 'Autoreduction_QueueProcessor_Test', False, ACTIVEMQ['SSL'])
        cls._client.connect()
        
        def mockSend(destination, message, persistent='true', priority='4', delay=None):
            headers = {'destination':destination, 'persistent':persistent, 'priority':priority}
            cls._client._listener.on_message(headers, message)
        cls._client.send = mockSend
        
        cls._timeout_wait = 1

        map(copyScripts, ['valid', 'empty_script', 'duplicate_var_reduce', 'syntax_error', 'new_instrument', 'InactiveInstrument', 'ExistingTestInstrument1'] )
    
    @classmethod
    def tearDownClass(cls):
        map(removeScripts, ['valid', 'empty_script', 'duplicate_var', 'syntax_error', 'new_instrument', 'InactiveInstrument', 'ExistingTestInstrument1'])
        pass
        
    def createMockSMTP(self):
        self.sentEmails = []
        parent = self
        
        class mockSMTP:
            def __init__(self, *args, **kwargs):
                pass
            def sendmail(self, *args, **kwargs):
                parent.sentEmails.append(args)
            def close(self):
                pass
                
        return mockSMTP
        

    '''
        Insert a reduction run to ensure the QueueProcessor can find one when recieving a topic message
    '''
    def insert_run(self, experiment, run_number=1, run_version=0, instrument="TestInstrument", data="/false/path"):
        ins, created = Instrument.objects.get_or_create(name=instrument)
        run = ReductionRun(run_number=run_number, instrument=ins, experiment=experiment, run_version=run_version, status=StatusUtils().get_queued())
        run.save()
        data_location = DataLocation(file_path=data, reduction_run=run)
        data_location.save()
        return run

    '''
        Check that a reduction run matches the values in the dictionary used to create it
    '''
    def assert_run_match(self, data_dict, reduction_run):
        self.assertEqual(reduction_run.instrument.name, data_dict["instrument"], "Expecting instrument to be %s but was %s" % (data_dict["instrument"], reduction_run.instrument.name))
        self.assertEqual(reduction_run.run_number, data_dict["run_number"], "Expecting run_number to be %s but was %s" % (data_dict["run_number"], reduction_run.run_number))
        self.assertEqual(reduction_run.experiment.reference_number, data_dict["rb_number"], "Expecting rb_number to be %s but was %s" % (data_dict["rb_number"], reduction_run.experiment.reference_number))

    '''
        Get a new RB Number to prevent conflicts
    '''
    def get_rb_number(self):
        global rb_number
        rb_number += 1
        return rb_number

    '''
        Create dummy variables for a given instrument
    '''
    def create_instrument_variables(self, instrument_name):
        instrument, created = Instrument.objects.get_or_create(name=instrument_name)
        instrument_variables = InstrumentVariable(instrument=instrument, start_run=0,name='TEST_NAME',value='TEST_VALUE', type='String')
        instrument_variables.save()

    '''
        Copy a test reduce.py script to the correct location for use in the tests
    '''
    def save_dummy_reduce_script(self, instrument_name):
        directory = TEST_REDUCTION_DIRECTORY % instrument_name
        test_reduce = os.path.join(os.path.dirname(__file__), '../', 'test_files','reduce.py')
        if not os.path.exists(directory):
            os.makedirs(directory)
        file_path = os.path.join(directory, 'reduce.py')
        if not os.path.isfile(file_path):
            shutil.copyfile(test_reduce, file_path)

    '''
        Remove dummy script file. 
        WARNING!!!! Destructive!!!
    '''
    def remove_dummy_reduce_script(self, instrument_name):
        directory = TEST_REDUCTION_DIRECTORY % instrument_name
        logging.warning("About to remove %s" % directory)
        if os.path.exists(directory):
            shutil.rmtree(directory)

    '''
        Create a new reduction run and check that it auto-creates an instrument when it doesn't exist
    '''
    def test_data_ready_new_instrument(self):
        rb_number = self.get_rb_number()
        instrument_name = "valid"
        self.assertEqual(Instrument.objects.filter(name=instrument_name).first(), None, "Wasn't expecting to find %s" % instrument_name)
        test_data = {
            "run_number" : 1,
            "instrument" : instrument_name,
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/DataReady', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        runs = ReductionRun.objects.filter(experiment=experiment, run_number=1)

        self.assertFalse(created, "Experiment should already exist.")
        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Queued", "Expecting status to be 'Queued' but was '%s'" % runs[0].status)
        instrument = Instrument.objects.filter(name=instrument_name).first()
        self.assertNotEqual(instrument, None, "Was expecting to find %s" % instrument_name)
        self.assertTrue(instrument.is_active, "Was expecting instrument to be active")

    '''
        Create a new reduction run and check that it auto-creates an instrument and its variables
    '''
    def test_data_ready_new_instrument_instrument_variables(self):
        rb_number = self.get_rb_number()
        instrument_name = "valid"
        self.assertEqual(Instrument.objects.filter(name=instrument_name).first(), None, "Wasn't expecting to find %s" % instrument_name)
        test_data = {
            "run_number" : 1,
            "instrument" : instrument_name,
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/DataReady', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        runs = ReductionRun.objects.filter(experiment=experiment, run_number=1)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Queued", "Expecting status to be 'Queued' but was '%s'" % runs[0].status)
        instrument = Instrument.objects.filter(name=instrument_name).first()
        self.assertNotEqual(instrument, None, "Was expecting to find %s" % instrument_name)
        self.assertTrue(instrument.is_active, "Was expecting instrument to be active")
        instrument_variables = InstrumentVariable.objects.filter(instrument=instrument, start_run__lte=1)
        self.assertNotEqual(instrument_variables, None, "Was expecting to find some instrument variables")
        self.assertTrue(len(instrument_variables) > 0, "Was expecting to find some instrument variables")
        self.assertNotEqual(instrument_variables[0].name, None, "Was expecting to find an instrument variable name")
        self.assertNotEqual(instrument_variables[0].value, None, "Was expecting to find an instrument variable value")
        self.assertNotEqual(instrument_variables[0].type, None, "Was expecting to find an instrument variable type")
    '''
        Create a new reduction run on an instrument that already exists
    '''
    def test_data_ready_existing_instrument(self):
        rb_number = self.get_rb_number()
        instrument_name = "valid"
        self.create_instrument_variables(instrument_name)
        self.assertNotEqual(Instrument.objects.filter(name=instrument_name).first(), None, "Was expecting to find %s" % instrument_name)
        test_data = {
            "run_number" : 1,
            "instrument" : instrument_name,
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/DataReady', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        runs = ReductionRun.objects.filter(experiment=experiment, run_number=1)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Queued", "Expecting status to be 'Queued' but was '%s'" % runs[0].status)
        self.assertNotEqual(Instrument.objects.filter(name=instrument_name).first(), None, "Was expecting to find %s" % instrument_name)

    '''
        Create a new reduction run on an instrument that already exists
    '''
    def test_data_ready_inactive_instrument(self):
        rb_number = self.get_rb_number()
        instrument_name = "InactiveInstrument"
        instrument = Instrument.objects.filter(name=instrument_name).first()
        self.assertNotEqual(instrument, None, "Was expecting to find %s" % instrument_name)
        self.assertFalse(instrument.is_active, "Was expecting %s to be inactive" % instrument_name)
        test_data = {
            "run_number" : 1,
            "instrument" : instrument_name,
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/DataReady', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        runs = ReductionRun.objects.filter(experiment=experiment, run_number=1)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Queued", "Expecting status to be 'Queued' but was '%s'" % runs[0].status)
        instrument = Instrument.objects.filter(name=instrument_name).first()
        self.assertNotEqual(instrument, None, "Was expecting to find %s" % instrument_name)
        self.assertTrue(instrument.is_active, "Was expecting %s to be active" % instrument_name)

    '''
        Create two new reduction runs for the same experiment
    '''
    def test_data_ready_multiple_runs(self):
        rb_number = self.get_rb_number()
        instrument_name = "valid"
        test_data_run_1 = {
            "run_number" : 1,
            "instrument" : instrument_name,
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        test_data_run_2 = {
            "run_number" : -2,
            "instrument" : instrument_name,
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/DataReady', json.dumps(test_data_run_1))
        self._client.send('/queue/DataReady', json.dumps(test_data_run_2))
        #time.sleep(self._timeout_wait)

        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 2, "Should only return 2 reduction runs but returned %s" % len(runs))
        self.assert_run_match(test_data_run_1, runs[0])
        self.assertEqual(str(runs[0].status), "Queued", "Expecting status to be 'Queued' but was '%s'" % runs[0].status)
        self.assert_run_match(test_data_run_2, runs[1])
        self.assertEqual(str(runs[1].status), "Queued", "Expecting status to be 'Queued' but was '%s'" % runs[1].status)

        
    '''
        Change an existing reduction run from Queued to Started
    '''
    def test_reduction_started_reduction_run_exists(self):
        rb_number = self.get_rb_number()
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        self.insert_run(run_number=1, instrument="valid", experiment=experiment)

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/ReductionStarted', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Processing", "Expecting status to be 'Processing' but was '%s'" % runs[0].status)

    '''
        Attempt to change a non-existing reduction run from Queued to Started
    '''
    def test_reduction_started_reduction_run_doesnt_exist(self):
        rb_number = self.get_rb_number()
        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/ReductionStarted', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 0, "Shouldn't return any reduction runs but returned %s" % len(runs))

    '''
        Attempt to (incorrectly) start an already started reduction run
    '''
    def test_reduction_started_reduction_run_already_started(self):
        rb_number = self.get_rb_number()
        started_time = timezone.now().replace(microsecond=0)
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        run = self.insert_run(run_number=1, instrument="valid", experiment=experiment)
        run.status = StatusUtils().get_processing()
        run.started = started_time
        run.save()

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/ReductionStarted', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Processing", "Expecting status to be 'Processing' but was '%s'" % runs[0].status)
        self.assertEqual(runs[0].started, started_time, "Started time should not have been updated")

    '''
        Attempt to (incorrectly) start a reduction run that has already completed
    '''
    def test_reduction_started_reduction_run_already_completed(self):
        rb_number = self.get_rb_number()
        started_time = timezone.now().replace(microsecond=0)
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        run = self.insert_run(run_number=1, instrument="valid", experiment=experiment)
        run.status = StatusUtils().get_completed()
        run.started = started_time
        run.save()

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/ReductionStarted', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Completed", "Expecting status to be 'Completed' but was '%s'" % runs[0].status)
        self.assertEqual(runs[0].started, started_time, "Started time should not have been updated")

    '''
        Re-start a reduction run than had previously shown an error
    '''
    def test_reduction_started_reduction_run_error(self):
        rb_number = self.get_rb_number()
        started_time = timezone.now().replace(microsecond=0)
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        run = self.insert_run(run_number=1, instrument="valid", experiment=experiment)
        run.status = StatusUtils().get_error()
        run.started = started_time
        run.save()
        #Sleep so started time can change
        time.sleep(self._timeout_wait)

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/ReductionStarted', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Processing", "Expecting status to be 'Processing' but was '%s'" % runs[0].status)
        self.assertNotEqual(runs[0].started, started_time, "Started time should have been updated")

    '''
        Change a started reduction run to completed
    '''
    def test_reduction_complete_reduction_run_exists(self):
        rb_number = self.get_rb_number()
        started_time = timezone.now().replace(microsecond=0)
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        run = self.insert_run(run_number=1, instrument="valid", experiment=experiment)
        run.status = StatusUtils().get_processing()
        run.started = started_time
        run.save()

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/ReductionComplete', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Completed", "Expecting status to be 'Completed' but was '%s'" % runs[0].status)
        self.assertNotEqual(runs[0].finished, None, "Expected the reduction run to have a finished timestamp")

    '''
        Attempt to complete a reduction run that doesn't exist
    '''
    def test_reduction_complete_reduction_run_doesnt_exists(self):
        rb_number = self.get_rb_number()

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/ReductionComplete', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 0, "Should only return 0 reduction runs but returned %s" % len(runs))

    '''
        Attempt to (incorrectly) complete a queued reduction run
    '''
    def test_reduction_complete_reduction_run_queued(self):
        rb_number = self.get_rb_number()
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        run = self.insert_run(run_number=1, instrument="valid", experiment=experiment)
        run.status = StatusUtils().get_queued()
        run.save()

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/ReductionComplete', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Queued", "Expecting status to be 'Queued' but was '%s'" % runs[0].status)
        self.assertEqual(runs[0].started, None, "Not expecting the reduction run to have a started timestamp")
        self.assertEqual(runs[0].finished, None, "Not expecting the reduction run to have a finished timestamp")

    '''
        Attempt to (incorrectly) complete a completed reduction run
    '''
    def test_reduction_complete_reduction_run_complete(self):
        rb_number = self.get_rb_number()
        started_time = timezone.now().replace(microsecond = 0)
        finished_time = timezone.now().replace(microsecond = 0)
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        run = self.insert_run(run_number=1, instrument="valid", experiment=experiment)
        run.status = StatusUtils().get_completed()
        run.started = started_time
        run.finished = finished_time
        run.save()

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/ReductionComplete', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Completed", "Expecting status to be 'Completed' but was '%s'" % runs[0].status)
        self.assertEqual(runs[0].started, started_time, "Not expecting the reduction run start to have changed. Was expecting %s but got %s" % (started_time, runs[0].started))
        self.assertEqual(runs[0].finished, finished_time, "Not expecting the reduction run finish to have changed. Was expecting %s but got %s" % (finished_time, runs[0].finished))

    '''
        Attempt to (incorrectly) complete a reduction run with an error
    '''
    def test_reduction_complete_reduction_run_error(self):
        rb_number = self.get_rb_number()
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        run = self.insert_run(run_number=1, instrument="valid", experiment=experiment)
        run.status = StatusUtils().get_error()
        run.save()

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        self._client.send('/queue/ReductionComplete', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Error", "Expecting status to be 'Error' but was '%s'" % runs[0].status)
        self.assertEqual(runs[0].started, None, "Not expecting the reduction run to have a started timestamp")
        self.assertEqual(runs[0].finished, None, "Not expecting the reduction run to have a finished timestamp")

    '''
        Set a reduction run as having an error
    '''
    def test_reduction_error_reduction_run_exists(self):
        rb_number = self.get_rb_number()
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        self.insert_run(run_number=1, instrument="valid", experiment=experiment)
        error_message = "We have an error here"

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0,
            "message" : error_message
        }
        
        with patch('smtplib.SMTP', self.createMockSMTP()):
            self._client.send('/queue/ReductionError', json.dumps(test_data))

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Error", "Expecting status to be 'Error' but was '%s'" % runs[0].status)
        self.assertEqual(runs[0].message, error_message, "Expecting the error message to be populated")
        self.assertNotEqual(self.sentEmails, [], "Expected a notification email to be sent")

    '''
        Set a reduction run as having an error
    '''
    def test_reduction_error_reduction_run_exists_no_message(self):
        rb_number = self.get_rb_number()
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        self.insert_run(run_number=1, instrument="valid", experiment=experiment)

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        
        with patch('smtplib.SMTP', self.createMockSMTP()):
            self._client.send('/queue/ReductionError', json.dumps(test_data))

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assert_run_match(test_data, runs[0])
        self.assertEqual(str(runs[0].status), "Error", "Expecting status to be 'Error' but was '%s'" % runs[0].status)
        self.assertEqual(runs[0].message, '', "Not expecting the error message to be populated but was '%s'" % runs[0].message)

    '''
        Set a reduction run as having an error
    '''
    def test_reduction_error_reduction_run_doesnt_exists(self):
        rb_number = self.get_rb_number()

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0
        }
        
        with patch('smtplib.SMTP', self.createMockSMTP()):
            self._client.send('/queue/ReductionError', json.dumps(test_data))

        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 0, "Should only return 0 reduction runs but returned %s" % len(runs))

    '''
        Check that all .png files are read as graphs
    '''
    def test_graphs_correctly_read_single(self):
        data_path = '/tmp/test_data/test_graphs_correctly_read_single/'
        if not os.path.exists(data_path):
            os.makedirs(data_path)
        test_graph = os.path.join(os.path.dirname(__file__), '../', 'test_files','test_graph.png')
        file_path = os.path.join(data_path, 'test_graph.png')
        if not os.path.isfile(file_path):
            shutil.copyfile(test_graph, file_path)

        rb_number = self.get_rb_number()
        started_time = timezone.now().replace(microsecond=0)
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        run = self.insert_run(run_number=1, instrument="valid", experiment=experiment)
        run.status = StatusUtils().get_processing()
        run.started = started_time
        run.save()

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0,
            "reduction_data" : [data_path]
        }
        self._client.send('/queue/ReductionComplete', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assertEqual(str(runs[0].status), "Completed", "Expecting status to be 'Completed' but was '%s'" % runs[0].status)
        self.assertNotEqual(runs[0].finished, None, "Expected the reduction run to have a finished timestamp")
        self.assertNotEqual(runs[0].graph, None, "Expected to find some graphs")
        self.assertTrue(len(runs[0].graph) == 1, "Expected to find 1 graph but instead found %s" % len(runs[0].graph))
        self.assertTrue('base64' in runs[0].graph[0], "Expected to find 'base64' in graph text")

    '''
        Check that all .png files are read as graphs
    '''
    def test_graphs_correctly_read_multiple(self):
        data_path = '/tmp/test_data/test_graphs_correctly_read_multiple/'
        if not os.path.exists(data_path):
            os.makedirs(data_path)
        try:
            test_graph = os.path.join(os.path.dirname(__file__), '../', 'test_files','test_graph.png')
            file_path = os.path.join(data_path, 'test_graph1.png')
            if not os.path.isfile(file_path):
                shutil.copyfile(test_graph, file_path)
            file_path = os.path.join(data_path, 'test_graph2.png')
            if not os.path.isfile(file_path):
                shutil.copyfile(test_graph, file_path)

            rb_number = self.get_rb_number()
            started_time = timezone.now().replace(microsecond=0)
            experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
            run = self.insert_run(run_number=1, instrument="valid", experiment=experiment)
            run.status = StatusUtils().get_processing()
            run.started = started_time
            run.save()

            test_data = {
                "run_number" : 1,
                "instrument" : "valid",
                "rb_number" : rb_number,
                "data" : "/false/path",
                "run_version" : 0,
                "reduction_data" : [data_path]
            }
            self._client.send('/queue/ReductionComplete', json.dumps(test_data))
            #time.sleep(self._timeout_wait)

            runs = ReductionRun.objects.filter(experiment=experiment)

            self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
            self.assertEqual(str(runs[0].status), "Completed", "Expecting status to be 'Completed' but was '%s'" % runs[0].status)
            self.assertNotEqual(runs[0].finished, None, "Expected the reduction run to have a finished timestamp")
            self.assertNotEqual(runs[0].graph, None, "Expected to find some graphs")
            self.assertTrue(len(runs[0].graph) == 2, "Expected to find 2 graph but instead found %s" % len(runs[0].graph))
            self.assertTrue('base64' in runs[0].graph[0], "Expected to find 'base64' in graph text")
            self.assertTrue('base64' in runs[0].graph[1], "Expected to find 'base64' in graph text")
        finally:
            if os.path.exists(data_path):
                shutil.rmtree(data_path)

    '''
        Check that all .png files are read as graphs
    '''
    def test_graphs_correctly_read_case_sensitive(self):
        data_path = '/tmp/test_data/test_graphs_correctly_read_case_sensitive/'
        if not os.path.exists(data_path):
            os.makedirs(data_path)
        test_graph = os.path.join(os.path.dirname(__file__), '../', 'test_files','test_graph.png')
        file_path = os.path.join(data_path, 'test_graph.PNG')
        if not os.path.isfile(file_path):
            shutil.copyfile(test_graph, file_path)

        rb_number = self.get_rb_number()
        started_time = timezone.now().replace(microsecond=0)
        experiment, created = Experiment.objects.get_or_create(reference_number=rb_number)
        run = self.insert_run(run_number=1, instrument="valid", experiment=experiment)
        run.status = StatusUtils().get_processing()
        run.started = started_time
        run.save()

        test_data = {
            "run_number" : 1,
            "instrument" : "valid",
            "rb_number" : rb_number,
            "data" : "/false/path",
            "run_version" : 0,
            "reduction_data" : [data_path]
        }
        self._client.send('/queue/ReductionComplete', json.dumps(test_data))
        #time.sleep(self._timeout_wait)

        runs = ReductionRun.objects.filter(experiment=experiment)

        self.assertEqual(len(runs), 1, "Should only return 1 reduction run but returned %s" % len(runs))
        self.assertEqual(str(runs[0].status), "Completed", "Expecting status to be 'Completed' but was '%s'" % runs[0].status)
        self.assertNotEqual(runs[0].finished, None, "Expected the reduction run to have a finished timestamp")
        self.assertNotEqual(runs[0].graph, None, "Expected to find some graphs")
        self.assertTrue(len(runs[0].graph) == 1, "Expected to find 1 graph but instead found %s" % len(runs[0].graph))
        self.assertTrue('base64' in runs[0].graph[0], "Expected to find 'base64' in graph text")  
   
   
class ICATCommunicationTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.test_user = 18187
        self.test_user_not_instrument_scientist = 13562
        self.test_instrument_scientist = 5818
        self.test_experiment = 1190070
        self.test_instrument = "GEM"

    '''
        Check that ICAT can login using the credentials found in settings.py
    '''
    def test_icat_login_with_setting_values(self):
        with ICATCommunication() as icat:
            pass

    '''
        Check that ICAT fails to login using invalid credentials
    '''
    def test_icat_login_with_invalid_credentials(self):
        try:
            with ICATCommunication(USER='MadeUp') as icat:
                self.assertEqual(icat, None, "Expecting login to fail")
        except ICATSessionError:
            pass
    
    '''
        Check that ICAT fails to login using invalid URL
    '''
    def test_icat_login_with_invalid_url(self):
        try:
            with ICATCommunication(URL='https://www.example.com/') as icat:
                self.assertEqual(icat, None, "Expecting login to fail")
        except SAXParseException:
            pass

    '''
        Check that ICAT can login when passed in credentials
    '''
    def test_icat_login_with_valid_values_passed_in(self):
        with ICATCommunication(**ICAT) as icat:
            pass
        
    '''
        Check that ICAT returns experiment details correctly
    '''
    def test_get_experiment_details_existing_experiment(self):
        with ICATCommunication() as icat:
            experiment = icat.get_experiment_details(self.test_experiment)
            
            self.assertNotEqual(experiment, None, 'Expecting an experiment to be returned')
            self.assertEqual(experiment['reference_number'], str(self.test_experiment), 'Expecting reference number to be %s to was %s instead' % (str(self.test_experiment), experiment['reference_number']))
            self.assertEqual(experiment['instrument'], 'GEM', 'Expecting instrument to be %s to was %s instead' % ('GEM', experiment['instrument']))

    '''
        Check that nothing is returned for an invalid experiment
    '''
    def test_get_experiment_details_invalid_experiment(self):
        with ICATCommunication() as icat:
            reference_number = -123333
            shouldBeReturned = {'reference_number': str(reference_number), 'end_date': 'N/A', 'title': 'N/A', 'summary': u'N/A', 'pi':'', 'start_date': 'N/A'}
            
            experiment = icat.get_experiment_details(reference_number)            
            self.assertEqual(experiment, shouldBeReturned, 'Expecting %s to be returned, but got %s' % (str(shouldBeReturned), str(experiment)))

    '''
        Check that an error is raised when passing in invalid values
    '''
    def test_get_experiment_details_invalid_input_number_string(self):
        with ICATCommunication() as icat:
            try:
                experiment = icat.get_experiment_details('123')
                self.fail("Expecting a TypeError to be thrown")
            except TypeError:
                pass
        
    '''
        Check that an error is raised when passing in invalid values
    '''
    def test_get_experiment_details_invalid_input_char_string(self):
        with ICATCommunication() as icat:
            try:
                experiment = icat.get_experiment_details('abc')
                self.fail("Expecting a TypeError to be thrown")
            except TypeError:
                pass

    '''
        Check that ICAT returns a set of instruments
    '''
    def test_get_valid_instruments_successful(self):
        with ICATCommunication() as icat:
            instruments = icat.get_valid_instruments(self.test_user)
            
            self.assertNotEqual(instruments, None, "Expecting some instruments returned")
            self.assertTrue(len(instruments) > 0, "Expecting some instruments returned")
            self.assertTrue('GEM' in instruments, "Expecting GEM to be returned")
       
    '''
        Check that an empty set is returned for an invalid user
    ''' 
    def test_get_valid_instruments_invalid_user(self):
        with ICATCommunication() as icat:
            instruments = icat.get_valid_instruments(1)
            
            self.assertEqual(instruments, [], "Not expecting some instruments returned")
                    
    '''
        Check that an error is raised when passing in invalid values
    '''    
    def test_get_valid_instruments_invalid_input_number_string(self):
        with ICATCommunication() as icat:
            try:
                experiment = icat.get_valid_instruments('123')
                self.fail("Expecting a TypeError to be thrown")
            except TypeError:
                pass     

    '''
        Check that an error is raised when passing in invalid values
    '''
    def test_get_valid_instruments_invalid_input_char_string(self):
        with ICATCommunication() as icat:
            try:
                experiment = icat.get_valid_instruments('abc')
                self.fail("Expecting a TypeError to be thrown")
            except TypeError:
                pass

    '''
        Check that ICAT returns a set of instruments that at least contains all owned instruments
    '''
    def test_get_valid_instruments_contains_all_owned_instruments(self):
        with ICATCommunication() as icat:
            instruments = icat.get_valid_instruments(self.test_instrument_scientist)
            owned_instruments = icat.get_owned_instruments(self.test_instrument_scientist)
            
            self.assertNotEqual(instruments, None, "Expecting some valid instruments returned")
            self.assertNotEqual(owned_instruments, None, "Expecting some owned instruments returned")
            for instrument in owned_instruments:
                self.assertTrue(instrument in instruments, "Expecting %s from owned instruments to be in valid instruments")

    '''
        Check that ICAT returns a set of instruments
    '''
    def test_get_owned_instruments_as_instrument_scientist(self):
        with ICATCommunication() as icat:
            owned_instruments = icat.get_owned_instruments(self.test_instrument_scientist)
            
            self.assertNotEqual(owned_instruments, None, "Expecting some owned instruments returned")
            self.assertTrue(len(owned_instruments) > 0, "Expecting some owned instruments returned")
            self.assertTrue('EMU' in owned_instruments, "Expecting EMU to be returned")

    '''
        Check that and empty set is returned
    '''
    def test_get_owned_instruments_not_as_instrument_scientist(self):
        with ICATCommunication() as icat:
            owned_instruments = icat.get_owned_instruments(self.test_user_not_instrument_scientist)
            
            self.assertEqual(owned_instruments, [], "Not expecting some owned instruments returned")

    '''
        Check that and empty set is returned
    '''
    def test_get_owned_instruments_invalid_user(self):
        with ICATCommunication() as icat:
            owned_instruments = icat.get_owned_instruments(1)
            
            self.assertEqual(owned_instruments, [], "Not expecting some owned instruments returned")

    '''
        Check that an error is raised when passing in invalid values
    '''
    def test_get_owned_instruments_invalid_input_number_string(self):
        try:
            with ICATCommunication() as icat:
                owned_instruments = icat.get_owned_instruments('123')
                self.fail('Excpecting TypeError to be raised')
        except TypeError:
            pass                

    '''
        Check that an error is raised when passing in invalid values
    '''
    def test_get_owned_instruments_invalid_input_char_string(self):
        try:
            with ICATCommunication() as icat:
                owned_instruments = icat.get_owned_instruments('abc')
                self.fail('Excpecting TypeError to be raised')
        except TypeError:
            pass

    '''
        Check that ICAT returns true when a user is on an experiment team
    '''
    def test_is_on_experiment_team_true(self):
        with ICATCommunication() as icat:
            is_on_team = icat.is_on_experiment_team(self.test_experiment, self.test_user)
            
            self.assertTrue(is_on_team, "Expecting to be on experiment team")

    '''
        Check that ICAT returns false when a user is not on an experiment team
    '''
    def test_is_on_experiment_team_false(self):
        with ICATCommunication() as icat:
            is_on_team = icat.is_on_experiment_team(self.test_experiment, self.test_instrument_scientist)
            
            self.assertFalse(is_on_team, "Not expecting to be on experiment team")

    '''
        Check that ICAT returns false when a user isn't found
    '''
    def test_is_on_experiment_team_invalid_user(self):
        with ICATCommunication() as icat:
            is_on_team = icat.is_on_experiment_team(self.test_experiment, 1)
            
            self.assertFalse(is_on_team, "Not expecting to be on experiment team")

    '''
        Check that ICAT returns false when an experiment isn't found
    '''
    def test_is_on_experiment_team_invalid_experiment(self):
        with ICATCommunication() as icat:
            is_on_team = icat.is_on_experiment_team(1, self.test_user)
            
            self.assertFalse(is_on_team, "Not expecting to be on experiment team")

    '''
        Check that an error is raised when passing in invalid values
    '''
    def test_is_on_experiment_team_invalid_input_number_string_experiment(self):
        try:
            with ICATCommunication() as icat:
                is_on_team = icat.is_on_experiment_team('123', self.test_user)
                self.fail("Expecting a TypeError to be raised")
        except TypeError:
            pass

    '''
        Check that an error is raised when passing in invalid values
    '''
    def test_is_on_experiment_team_invalid_input_char_string_experiment(self):
        try:
            with ICATCommunication() as icat:
                is_on_team = icat.is_on_experiment_team('abc', self.test_user)
                self.fail("Expecting a TypeError to be raised")
        except TypeError:
            pass

    '''
        Check that an error is raised when passing in invalid values
    '''
    def test_is_on_experiment_team_invalid_input_number_string_user(self):
        try:
            with ICATCommunication() as icat:
                is_on_team = icat.is_on_experiment_team(self.test_experiment, '123')
                self.fail("Expecting a TypeError to be raised")
        except TypeError:
            pass

    '''
        Check that an error is raised when passing in invalid values
    '''
    def test_is_on_experiment_team_invalid_input_char_string_user(self):
        try:
            with ICATCommunication() as icat:
                is_on_team = icat.is_on_experiment_team(self.test_experiment, 'abc')
                self.fail("Expecting a TypeError to be raised")
        except TypeError:
            pass

    '''
        Check that ICAT returns a set containing experiment reference numbers
    '''
    def test_get_associated_experiments_successful(self):
        with ICATCommunication() as icat:
            experiments = icat.get_associated_experiments(self.test_user)
            
            self.assertNotEqual(experiments, None, "Expecting some experiments to be returned")
            self.assertTrue(len(experiments) > 0, "Expecting some experiments to be returned")
            self.assertTrue(str(self.test_experiment) in experiments, "Expecting to find %s in the list of experiments" % str(self.test_experiment))
    
    '''
        Check that ICAT returns and empty set when the user is not found
    '''
    def test_get_associated_experiments_invalid_user(self):
        with ICATCommunication() as icat:
            experiments = icat.get_associated_experiments(1)
            
            self.assertEqual(experiments, [], "Not expecting some experiments to be returned")
                
    '''
        Check that an error is raised when passing in invalid values
    '''        
    def test_get_associated_experiments_invalid_input_number_string(self):
        try:
            with ICATCommunication() as icat:
                experiments = icat.get_associated_experiments('123')
                self.fail("Expecting a TypeError to be raised")
        except TypeError:
            pass

    '''
        Check that an error is raised when passing in invalid values
    '''
    def test_get_associated_experiments_invalid_input_char_string(self):
        try:
            with ICATCommunication() as icat:
                experiments = icat.get_associated_experiments('abc')
                self.fail("Expecting a TypeError to be raised")
        except TypeError:
            pass
    
    '''
        Check that experiments can be returned to a list of instruments
    '''
    def test_get_valid_experiments_for_instruments_valid_user_valid_instruments(self):
        with ICATCommunication() as icat:
            instruments = icat.get_valid_experiments_for_instruments(self.test_user, [self.test_instrument])
            
            self.assertNotEqual(instruments, None, "Expecting some experiments to be returned")
            self.assertTrue(len(instruments) > 0, "Expecting some experiments to be returned")

            found_experiment = False
            for instrument in instruments:
                for experiment in instruments[instrument]:
                    if experiment == str(1290075):
                        found_experiment = True
                        break
            self.assertTrue(found_experiment, "Expecting to find experiment %s, but only received %s" % (1290075, str(instruments)))
              
    '''
        Check that an exception is raised when no instruments are passed in
    '''
    def test_get_valid_experiments_for_instruments_valid_user_empty_instruments(self):
        try:
            with ICATCommunication() as icat:
                experiments = icat.get_valid_experiments_for_instruments(self.test_user, [])
                self.fail("Expecting an Exception to be raised")
        except Exception:
            pass

    '''
        Check that an exception is raised when an invalid user is passed in
    '''
    def test_get_valid_experiments_for_instruments_invalid_user_empty_instruments(self):
        try:
            with ICATCommunication() as icat:
                experiments = icat.get_valid_experiments_for_instruments('123', [])
                self.fail("Expecting an TypeError to be raised")
        except TypeError:
            pass

    '''
        Check that a user is an admin
    '''
    def test_is_admin(self):
        with ICATCommunication() as icat:
            is_admin = icat.is_admin(self.test_user)

            self.assertTrue(is_admin, "Expecting user %s to be an admin." % self.test_user)

    '''
        Check that a user is not an admin
    '''
    def test_is_not_admin(self):
        with ICATCommunication() as icat:
            is_admin = icat.is_admin(self.test_instrument_scientist)

            self.assertFalse(is_admin, "Not expecting user %s to be an admin." % self.test_instrument_scientist)
         
         
class UOWSClientTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.uows = UOWSClient(URL=UOWS_URL)
        
        print('\nThese tests require that you have a user account on the user office system.')
        cls._username = raw_input('UserOffice WebService Username: ')
        cls._password = getpass.getpass('UserOffice WebService Password: ')
        client = suds_client(UOWS_URL)
        cls._session_id = client.service.login(cls._username, cls._password)
        
    @classmethod
    def tearDownClass(cls):
        client = suds_client(UOWS_URL)
        try:
            client.service.logout(cls._session_id)
        except:
            pass        
        
    def setUp(self):
        pass
        
    def tearDown(self):
        pass
        
    '''
        Check that a valid session is correctly identified
    '''
    def test_check_session_of_valid_sessionid(self):
        session_id = self._session_id

        is_valid = self.uows.check_session(session_id)

        self.assertTrue(is_valid, "Expecting Session ID to be valid")

    '''
        Check that an invalid session is correctly identified
    '''
    def test_check_session_of_invalid_sessionid(self):
        session_id = '123'

        is_valid = self.uows.check_session(session_id)

        self.assertFalse(is_valid, "Expecting Session ID to be invalid")

    '''
        Check that an invalid session is correctly identified
    '''
    def test_check_session_of_invalid_sessionid_chars(self):
        session_id = 'abc'

        is_valid = self.uows.check_session(session_id)

        self.assertFalse(is_valid, "Expecting Session ID to be invalid")

    '''
        Check that an invalid session is correctly identified
    '''
    def test_check_session_of_invalid_sessionid_none(self):
        session_id = None

        is_valid = self.uows.check_session(session_id)

        self.assertFalse(is_valid, "Expecting Session ID to be invalid")

    '''
        Check that a person is returned for a valid Session ID
    '''
    def test_get_person_valid_sessionid(self):
        session_id = self._session_id

        person = self.uows.get_person(session_id)

        self.assertNotEqual(person, None, "Expecting a person to be returned")
        self.assertNotEqual(person['email'], None, "Expecting the person to have an email")
        self.assertNotEqual(person['email'], '', "Expecting the person to have an email")
        self.assertNotEqual(person['first_name'], None, "Expecting the person to have a first name")
        self.assertNotEqual(person['first_name'], '', "Expecting the person to have a first name")
        self.assertNotEqual(person['last_name'], None, "Expecting the person to have a last name")
        self.assertNotEqual(person['last_name'], '', "Expecting the person to have a last name")
        self.assertNotEqual(person['usernumber'], None, "Expecting the person to have a user number")
        self.assertNotEqual(person['usernumber'], '', "Expecting the person to have a user number")

    '''
        Check that None is returned for an invalid Session ID
    '''
    def test_get_person_invalid_sessionid(self):
        session_id = '123'

        person = self.uows.get_person(session_id)

        self.assertEqual(person, None, "Not expecting a person to be returned")

    '''
        Check that None is returned for an invalid Session ID
    '''
    def test_get_person_invalid_sessionid_chars(self):
        session_id = 'abc'

        person = self.uows.get_person(session_id)

        self.assertEqual(person, None, "Not expecting a person to be returned")

    '''
        Check that None is returned for an invalid Session ID
    '''
    def test_get_person_invalid_sessionid_none(self):
        session_id = None

        person = self.uows.get_person(session_id)

        self.assertEqual(person, None, "Not expecting a person to be returned")

    '''
        Check that a Session ID is invalidated on logout
    '''
    def test_logout_valid_sessionid(self):
        session_id = self._session_id
        try:
            person = self.uows.logout(session_id)
            is_valid = self.uows.check_session(session_id)
            self.assertFalse(is_valid, "Expecting Session ID to be invalid")
        except:
            self.fail("Wasn't expecting an exception")

    '''
        Check that calling logout with an invalidated Session ID doesn't throw an exception
    '''
    def test_logout_invalid_sessionid(self):
        session_id = '123'
        try:
            person = self.uows.logout(session_id)
        except:
            self.fail("Wasn't expecting an exception")

    '''
        Check that calling logout with an invalidated Session ID doesn't throw an exception
    '''
    def test_logout_invalid_sessionid_chars(self):
        session_id = 'abc'
        try:
            person = self.uows.logout(session_id)
        except:
            self.fail("Wasn't expecting an exception")

    '''
        Check that calling logout with an invalidated Session ID doesn't throw an exception
    '''
    def test_logout_invalid_sessionid_none(self):
        session_id = None
        try:
            person = self.uows.logout(session_id)
        except:
            self.fail("Wasn't expecting an exception")
            
            
            
            
            
            
            
            
            