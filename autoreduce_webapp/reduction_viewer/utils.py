import logging, os, sys
sys.path.append(os.path.join("../", os.path.dirname(os.path.dirname(__file__))))
os.environ["DJANGO_SETTINGS_MODULE"] = "autoreduce_webapp.settings"
from autoreduce_webapp.settings import LOG_FILE, LOG_LEVEL, BASE_DIR
logging.basicConfig(filename=LOG_FILE,level=LOG_LEVEL)
from django.db import models
from reduction_viewer.models import Instrument, Status

class StatusUtils(object):
    def _get_status(self, status_value):
        status, created = Status.objects.get_or_create(value=status_value)
        if created:
            logging.warn("%s status was not found, created it." % status_value)
        return status

    def get_error(self):
        return self._get_status("Error")

    def get_completed(self):
        return self._get_status("Completed")

    def get_processing(self):
        return self._get_status("Processing")

    def get_queued(self):
        return self._get_status("Queued")
            
class InstrumentUtils(object):
    def get_instrument(self, instrument_name):
        instrument, created = Instrument.objects.get_or_create(name__iexact=instrument_name)
        if created:
            logging.warn("%s instrument was not found, created it." % instrument_name)
        return instrument