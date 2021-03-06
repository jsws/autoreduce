import icat
from settings import ACTIVE_MQ
from settings import ICAT
import stomp
import json
import sys
import argparse

def submit_run(active_mq_client, rb_number, instrument, data_file_location, run_number):
    data_dict = {"rb_number": rb_number,
                 "instrument": instrument,
                 "data": data_file_location,
                 "run_number": run_number,
                 "facility": "ISIS"
                }

    active_mq_client.send('/queue/DataReady', json.dumps(data_dict), priority=1)
    print("Submitted run: \r\n" + json.dumps(data_dict, indent=1))

'''
Gets the datafile from ICAT which contains the location and investigation of the datafile.
'''
def get_data_file(icat_client, instrument, run_number, file_ext):
    file_name = instrument + str(run_number).zfill(5) + "." + file_ext
    datafile = icat_client.search("SELECT df FROM Datafile df WHERE df.name = '" + file_name + "' INCLUDE df.dataset AS ds, ds.investigation")

    if not datafile:
        print("Cannot find datafile '" + file_name + "'. Will try with zeros in front of run number.")
        file_name = instrument + str(run_number).zfill(8) + "." + file_ext
        datafile = icat_client.search("SELECT df FROM Datafile df WHERE df.name = '" + file_name + "' INCLUDE df.dataset AS ds, ds.investigation")

    if not datafile:
        print("Cannot find datafile '" + file_name + "'. Exiting...")
        sys.exit(1)
    return datafile[0]

def main():
    parser = argparse.ArgumentParser(description='Submit a run to the autoreduction service.',
                                     epilog='./manual-submission.py GEM 83880 [-e 83882]')
    parser.add_argument('instrument', metavar='instrument', type=str,
                        help='a string of the instrument name e.g "GEM"')
    parser.add_argument('-e', metavar='end_run_number', nargs='?', type=int,
                        help='if submitting a range, the end run number e.g. "83882"')
    parser.add_argument('start_run_number', metavar='start_run_number', type=int,
                        help='the start run number e.g. "83880"')
    args = parser.parse_args()

    run_numbers = [args.start_run_number]

    if args.e:
        # Range submission
        if not args.e > args.start_run_number:
            print("'end_run_number' must be greater than 'start_run_number'.")
            print("e.g './manual-submission.py GEM 83880 -e 83882'")
            sys.exit(1)
        run_numbers = range(args.start_run_number, args.e + 1)

    print("Logging into ICAT")
    icat_client = icat.client.Client(ICAT['URL'])
    icat_client.login(ICAT['AUTH'], {'username': ICAT['USER'], 'password': ICAT['PASSWORD']})

    print("Logging into ActiveMQ " + ACTIVE_MQ['URL'])
    activemq_client = stomp.Connection([(ACTIVE_MQ['URL'], 61613)])
    activemq_client.start()
    activemq_client.connect(ACTIVE_MQ['USER'], ACTIVE_MQ['PASSWORD'], wait=True)

    instrument = args.instrument.upper()

    for run in run_numbers:
        datafile = get_data_file(icat_client, instrument, run, "nxs")

        location = datafile.location
        rb_num = datafile.dataset.investigation.name
        submit_run(activemq_client, rb_num, instrument, location, run)

if __name__ == "__main__":
    main()
