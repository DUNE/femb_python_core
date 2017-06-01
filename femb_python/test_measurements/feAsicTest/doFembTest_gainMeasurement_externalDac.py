from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from builtins import range
from builtins import int
from builtins import str
from builtins import hex
from future import standard_library
standard_library.install_aliases()
from builtins import object
import sys
import string
from subprocess import call
from time import sleep
import os
import ntpath
import glob
import struct
import json

from femb_python.configuration import CONFIG
from femb_python.write_data import WRITE_DATA
from femb_python.configuration.cppfilerunner import CPP_FILE_RUNNER

class FEMB_TEST_GAIN_EXTERNALDAC(object):

    def __init__(self, datadir="data"):

        #import femb_udp modules from femb_udp package
        self.femb_config = CONFIG()
        self.write_data = WRITE_DATA(datadir)
        #set appropriate packet size
        self.write_data.femb.MAX_PACKET_SIZE = 8000

        #set status variables
        self.status_check_setup = 0
        self.status_record_data = 0
        self.status_do_analysis = 0
        self.status_archive_results = 0
        self.cppfr = CPP_FILE_RUNNER()

        #misc variables
        self.gain = 0
        self.shape = 0
        self.base = 0

        #json output, note module version number defined here
        self.jsondict = {'type':'quadFeAsic_gain_externaldac'}
        self.jsondict['version'] = '1.0'
        self.jsondict['timestamp']  = str(self.write_data.date)

    def reset(self):
        self.status_check_setup = 0
        self.status_record_data = 0
        self.status_do_analysis = 0
        self.status_archive_results = 0

    def check_setup(self):
        #CHECK STATUS AND INITIALIZATION
        print("GAIN MEASUREMENT EXTERNAL DAC - CHECKING READOUT STATUS")
        self.status_check_setup = 0

        self.write_data.assure_filedir()

        #check if register interface is working
        print("Checking register interface")
        regVal = self.write_data.femb.read_reg(5)
        if (regVal == None) or (regVal == -1):
            print("Error running doFembTest - FEMB register interface is not working.")
            print(" Turn on or debug FEMB UDP readout.")       
            return
        print("Read register 5, value = " + str( hex( regVal ) ) )

        #initialize FEMB to known state
        print("Initializing board")
        self.femb_config.initBoard()

        #check if data streaming is working
        print("Checking data streaming")
        testData = self.write_data.femb.get_data_packets(1)
        if testData == None:
            print("Error running doFembTest - FEMB is not streaming data.")
            print(" Turn on and initialize FEMB UDP readout.")
            #print(" This script will exit now")
            #sys.exit(0)
            return
        if len(testData) == 0:
            print("Error running doFembTest - FEMB is not streaming data.")
            print(" Turn on and initialize FEMB UDP readout.")
            #print(" This script will exit now")
            #sys.exit(0)
            return

        print("Received data packet " + str(len(testData[0])) + " bytes long")

        #check for analysis executables
        if not self.cppfr.exists('test_measurements/example_femb_test/parseBinaryFile'):    
            print('parseBinaryFile not found, run setup.sh')
            #sys.exit(0)
            return

        print("GAIN MEASUREMENT EXTERNAL DAC - READOUT STATUS OK" + "\n")
        self.status_check_setup = 1

    def record_data(self):
        if self.status_check_setup == 0:
            print("Please run check_setup method before trying to take data")
            return
        if self.status_record_data == 1:
            print("Data already recorded. Reset/restat GUI to begin a new measurement")
            return
        #MEASUREMENT SECTION
        print("GAIN MEASUREMENT EXTERNAL DAC - RECORDING DATA")

        #initialize FEMB configuration to known state
        print("FE ASIC Settings: Gain " + str(self.gain) + ", Shaping Time " + str(self.shape) + ", Baseline " + str(self.base) )
        self.femb_config.feasicGain = self.gain
        self.femb_config.feasicShape = self.shape
        self.femb_config.feasicBaseline = self.base
        self.femb_config.configFeAsic()

        #disable pulser
        self.femb_config.setInternalPulser(0,0x0)
        self.femb_config.setDacPulser(0,0x0)
        self.femb_config.setFpgaPulser(0,0x0)

        #setup output file and record data
        self.write_data.filename = "rawdata_gainMeasurement_externaldac_%s_g_%d_s_%d_b_%d.bin" % \
                                   (self.write_data.date, self.gain, self.shape, self.base)

        print("Recording " + self.write_data.filename )
        self.write_data.numpacketsrecord = 50
        self.write_data.run = 0
        self.write_data.runtype = 0
        self.write_data.runversion = 0
        self.write_data.open_file()

        #take initial noise data run
        subrun = 0
        for asic in range(0,4,1):
            self.femb_config.turnOnAsic(asic)
            for asicCh in range(0,16,1):
                self.femb_config.selectChannel(asic,asicCh)
                self.write_data.record_data(subrun, asic, asicCh)
            
        #turn ASICs back on, start pulser section
        self.femb_config.feasicEnableTestInput = 1
        self.femb_config.turnOnAsics()
        subrun = 1
        #loop over pulser configurations, each configuration is it's own subrun
        for p in range(1,10,1):
            pVal = 1024 + int(p)*256
            self.femb_config.setDacPulser(1,pVal)
            print("Pulse amplitude " + str(pVal) )

            #loop over channels
            for asic in range(0,4,1):
                for asicCh in range(0,16,1):
                    self.femb_config.selectChannel(asic,asicCh)
                    self.write_data.record_data(subrun, asic, asicCh)

            #increment subrun, important
            subrun = subrun + 1

        #close file
        self.write_data.close_file()

        #turn off pulser
        self.femb_config.setDacPulser(0,0)

        #turn off ASICs
        self.femb_config.turnOffAsics()

        print("GAIN MEASUREMENT EXTERNAL DAC - DONE RECORDING DATA" + "\n")
        self.status_record_data = 1

    def do_analysis(self):
        if self.status_record_data == 0:
            print("Please record data before analysis")
            return
        if self.status_do_analysis == 1:
            print("Analysis already complete")
            return
        #ANALYSIS SECTION
        print("GAIN MEASUREMENT EXTERNAL DAC - ANALYZING AND SUMMARIZING DATA")

        #parse binary
        self.cppfr.run("test_measurements/feAsicTest/parseBinaryFile", [self.write_data.data_file_path])

        #run analysis program
        newName = "output_parseBinaryFile_gainMeasurement_externaldac_" + str(self.write_data.date) + ".root"
        newPath = os.path.join(self.write_data.filedir, newName)
        call(["mv", "output_parseBinaryFile.root" , newPath])
        self.cppfr.run("test_measurements/feAsicTest/processNtuple_gainMeasurement_externaldac",  [newPath])

        newName = "output_processNtuple_gainMeasurement_externaldac_" + str(self.write_data.date) + ".root"
        newPath = os.path.join(self.write_data.filedir, newName)
        call(["mv", "output_processNtuple_gainMeasurement.root" , newPath])
        
        newName = "summaryPlot_gainMeasurement_externaldac_" + str(self.write_data.date) + ".png"
        newPath = os.path.join(self.write_data.filedir, newName)
        call(["mv", "summaryPlot_gainMeasurement_externaldac.png" , newPath])

        newName = "results_gainMeasurement_externaldac_" + str(self.write_data.date) + ".list"
        newPath = os.path.join(self.write_data.filedir, newName)
        call(["mv", "output_processNtuple_gainMeasurement_externaldac.list" , newPath])

        #summary plot
        #print("GAIN MEASUREMENT - DISPLAYING SUMMARY PLOT, CLOSE PLOT TO CONTINUE")
        #call(["display", newPath])

        print("GAIN MEASUREMENT EXTERNAL DAC - DONE ANALYZING AND SUMMARIZING DATA" + "\n")
        self.status_do_analysis = 1

    def archive_results(self):
        #if self.status_do_analysis == 0:
        #    print("Please analyze data before archiving results")
        #    return
        #if self.status_archive_results == 1:
        #    print("Results already archived")
        #    return
        #ARCHIVE SECTION
        print("GAIN MEASUREMENT EXTERNAL DAC - ARCHIVE")

        #add summary variables to output
        self.jsondict['status_check_setup'] = str( self.status_check_setup )
        self.jsondict['status_record_data'] = str( self.status_record_data )
        self.jsondict['status_do_analysis'] = str( self.status_do_analysis )
        self.jsondict['filedir'] = str( self.write_data.filedir )
        self.jsondict['config_gain'] = str( self.gain )
        self.jsondict['config_shape'] = str( self.shape )
        self.jsondict['config_base'] = str( self.base )

        #parse the output results, kind of messy
        newName = "results_gainMeasurement_externaldac_" + str(self.write_data.date) + ".list"
        newPath = os.path.join(self.write_data.filedir, newName)

        lines = []
        with open( newPath ) as infile:
          for line in infile:
            line = line.strip('\n')
            line = line.split(',') #measurements separated by commas
            parseline = {}
            for n in range(0,len(line),1):
              word = line[n].split(' ')
              if( len(word) != 2 ):
                continue
              parseline[ str(word[0]) ] = str(word[1])
            lines.append(parseline)
        self.jsondict['results'] = lines
        jsonoutput = json.dumps(self.jsondict, indent=4, sort_keys=True)
        print( jsonoutput )
 
        #dump results into json
        newName = "results_gainMeasurement_externaldac_" + str(self.write_data.date) + ".json"
        newPath = os.path.join(self.write_data.filedir, newName)
        with open( newName , 'w') as outfile:
          json.dump(jsonoutput, outfile)
        call(["mv", newName , newPath ])

        #get required results from dict to propagate to GUI
        """
        asicStatus = []
        if "results" in self.jsondict:
          results = self.jsondict["results"]
          for d in results:
            if "asic" in d:
              asicNum = d["asic"]
              fail = d["fail"]
              asicStatus.append( [asicNum,fail] )
        """
        print("GAIN MEASUREMENT - DONE ARCHIVING" + "\n")
        self.status_archive_results = 1

def main():
    '''Create a FEMB_TEST_GAIN and run check/record/ana with given gain,
    shape and base indicides and femb number taken from parameter set
    stored in JSON file as only argument.
    '''

    import json
    params = json.loads(open(sys.argv[1]).read())

    datadir = params['datadir']
    ftg = FEMB_TEST_GAIN_EXTERNALDAC(datadir)
    ftg.gain = params['gain_ind']
    ftg.shape = params['shape_ind']
    ftg.base = params['base_ind']

    ftg.check_setup()
    ftg.record_data()
    ftg.do_analysis()
    ftg.archive_results()

if __name__ == '__main__':
    main()