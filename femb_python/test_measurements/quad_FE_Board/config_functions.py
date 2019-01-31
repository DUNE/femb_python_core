""" 
Board-specific function
"""

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from builtins import int
from builtins import range
from builtins import hex
from builtins import str
from future import standard_library
standard_library.install_aliases()
from builtins import object
from femb_python.generic_femb_udp import FEMB_UDP
from femb_python.test_measurements.quad_FE_Board.low_level_pre_udp import LOW_LEVEL
from femb_python.test_measurements.quad_FE_Board.sync_functions import SYNC_FUNCTIONS
from femb_python.configuration.FE_config import FE_CONFIG 
from femb_python.configuration.config_module_loader import getDefaultDirectory
import time
import matplotlib.pyplot as plt
import numpy as np
import os
import json

class FEMB_CONFIG_FUNCTIONS(object):
    """
    Base class for configuration files. These should be considered the 'public'
    methods of the config classes, non-configuration code should only use this set
    of functions.  
    """

    def __init__(self, config_file = None):
        """
        Initialize this class (no board communication here. Should setup self.femb_udp as a femb_udp instance, get FE Registers, etc...)
        """
        if (config_file == None):
            from femb_python.configuration import CONFIG
            self.config = CONFIG
        else:
            self.config = config_file
            
        self.femb_udp = FEMB_UDP(self.config)     
        self.low_func = LOW_LEVEL(self.config)
        self.sync_functions = SYNC_FUNCTIONS(self.config)
        self.FE_Regs = FE_CONFIG(chip_num = int(self.config["DEFAULT"]["NASICS"]), chn_num = int(self.config["DEFAULT"]["NASICCH"]))
        
        self.root_dir = getDefaultDirectory()
        file_name = os.path.join(self.root_dir,self.config["FILENAMES"]["DEFAULT_GUI_FILE_NAME"])
        if os.path.isfile(file_name):
            self.default_settings = dict()
            with open(file_name, 'r') as f:
                jsondata = json.load(f)
                for i in jsondata:
                    self.default_settings[i] = jsondata[i]
                    
        self.chip_ver = int(self.default_settings["chipver"])
        self.board_ver = self.default_settings["boardid"]

    def initBoard(self, **kwargs):
        """
        Initialize board/asics with default configuration
        """

        self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_MUX_MODE"]), int(self.config["INITIAL_SETTINGS"]["DEFAULT_MUX"]))
        self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_SS"]), int(self.config["INITIAL_SETTINGS"]["DEFAULT_SS"]))
        self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_TIMEOUT"]), int(self.config["INITIAL_SETTINGS"]["DEFAULT_TIMEOUT"], 16))
        self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_SAMPLESPEED"]), int(self.config["INITIAL_SETTINGS"]["DEFAULT_SAMPLE_SPEED"]))
        
        default_frame_size = 16 * (int(self.config["INITIAL_SETTINGS"]["DEFAULT_FRAME_SIZE"], 16)//16)
        self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_FRAME_SIZE"]), default_frame_size)
        
        self.low_func.setExternalPulser(val=int(self.config["INITIAL_SETTINGS"]["DEFAULT_EXTERNAL_DAC_VAL"], 16), 
                               period=int(self.config["INITIAL_SETTINGS"]["DEFAULT_EXTERNAL_DAC_TP_PERIOD"]), shift=int(self.config["INITIAL_SETTINGS"]["DEFAULT_EXTERNAL_DAC_TP_SHIFT"]), enable=False)
                       
        self.configFeAsic(test_cap="on", base="200mV", gain="14mV", shape="2us", monitor_ch=None, buffer="off", 
                       leak = "500pA", monitor_param = None, s16=None, acdc="dc", test_dac="test_off", dac_value=0)
        
        self.low_func.selectChipChannel(chip = 2, chn = 7)
        self.low_func.selectChipChannel(chip = 1, chn = 6)
        
        latch_settings_name = "{}_LATCH_SETTINGS".format(self.board_ver)
        phase_settings_name = "{}_PHASE_SETTINGS".format(self.board_ver)
        
        latch = []
        phase = []
        
        #This section loops through the categories to get the settings we want, since you can't make arrays in INI files
        try:
            latch_settings = list(self.config._sections["{}".format(latch_settings_name)].keys())
            phase_settings = list(self.config._sections["{}".format(phase_settings_name)].keys())
            
            for i in range(len(latch_settings)):
                latch.append(int(self.config["{}".format(latch_settings_name)][latch_settings[i]], 16))
            for i in range(len(phase_settings)):
                phase.append(int(self.config["{}".format(phase_settings_name)][phase_settings[i]], 16))
            
        except KeyError:
            print("config_functions --> No settings found for {} and {}!  Using defaults".format(latch_settings_name, phase_settings_name))
            latch_settings = list(self.config._sections["LATCH_SETTINGS_DEFAULT"].keys())
            phase_settings = list(self.config._sections["PHASE_SETTINGS_DEFAULT"].keys())
            
            for i in range(len(latch_settings)):
                latch.append(int(self.config["LATCH_SETTINGS_DEFAULT"][latch_settings[i]], 16))
            for i in range(len(phase_settings)):
                phase.append(int(self.config["PHASE_SETTINGS_DEFAULT"][phase_settings[i]], 16))
            
        for i,reg in enumerate(range(int(self.config["REGISTERS"]["REG_LATCH_MIN"]), int(self.config["REGISTERS"]["REG_LATCH_MAX"]) + 1, 1)):
            self.femb_udp.write_reg(reg, latch[i])
        for i,reg in enumerate(range(int(self.config["REGISTERS"]["REG_PHASE_MIN"]), int(self.config["REGISTERS"]["REG_PHASE_MAX"]) + 1, 1)):
            self.femb_udp.write_reg(reg, phase[i])
        self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_TEST_ADC"]), int(self.config["INITIAL_SETTINGS"]["DEFAULT_MONITOR_ADC_SETTINGS"], 16))
        
        self.SPI_array = self.writeFE()
        return self.SPI_array
    
    def writeFE(self):
        #Grab ASIC settings from linked class
        Feasic_regs = self.feasic_regs
        #note which sockets fail    
        #TODO get info from GUI to skip over certain chips
        config_list = [0,0,0,0]
        #Try 10 times (ocassionally it wont work the first time)
        for k in range(10):
            #Puts the settings in FPGA memory
            for i,regNum in enumerate(range(int(self.config["REGISTERS"]["REG_FESPI_BASE"]), int(self.config["REGISTERS"]["REG_FESPI_BASE"])+len(Feasic_regs), 1)):
                self.femb_udp.write_reg( regNum, Feasic_regs[i])
#                print (hex(Feasic_regs[i]))

            #Reset, then write twice to the ASICs
            reg = int(self.config["REGISTERS"]["REG_FEASIC_SPI"])
            reset = int(self.config["DEFINITIONS"]["FEASIC_SPI_RESET"])
            start = int(self.config["DEFINITIONS"]["FEASIC_SPI_START"])
            stop = int(self.config["DEFINITIONS"]["FEASIC_SPI_STOP"])
            self.femb_udp.write_reg ( reg, reset, doReadBack = False)
            self.femb_udp.write_reg ( reg, stop, doReadBack = False)
            time.sleep(.2)
            self.femb_udp.write_reg ( reg, start, doReadBack = False)
            self.femb_udp.write_reg ( reg, stop, doReadBack = False)
            time.sleep(.2)
            self.femb_udp.write_reg ( reg, start, doReadBack = False)
            self.femb_udp.write_reg ( reg, stop, doReadBack = False)
            time.sleep(.2)
            
            #The FPGA automatically compares the readback to check if it matches what was written.  That result is read back
            #A bit that's zero means the corresponding ASIC didn't write properly
            val = self.femb_udp.read_reg(reg) 
            wrong = False

            #check to see if everything went well, and return the status of the 4 chips in the array, so the sequence can notify/skip them
            if (((val & 0x10000) >> 16) != 1):
                print ("FEMB_CONFIG_BASE--> Something went wrong when programming FE 1")
                config_list[0] = 0
                wrong = True
            else:
                config_list[0] = 1
                
            if (((val & 0x20000) >> 17) != 1):
                print ("FEMB_CONFIG_BASE--> Something went wrong when programming FE 2")
                config_list[1] = 0
                wrong = True
            else:
                config_list[1] = 1
                
            if (((val & 0x40000) >> 18) != 1):
                print ("FEMB_CONFIG_BASE--> Something went wrong when programming FE 3")
                config_list[2] = 0
                wrong = True
            else:
                config_list[2] = 1
                
            if (((val & 0x80000) >> 19) != 1):
                print ("FEMB_CONFIG_BASE--> Something went wrong when programming FE 4")
                config_list[3] = 0
                wrong = True
            else:
                config_list[3] = 1

            if (wrong == True and k == 9):
                try:
                    print ("FEMB_CONFIG_BASE--> SPI_Status is {}").format(hex(val))
                except AttributeError:
                    print ("FEMB_CONFIG_BASE--> SPI_Status is NOT ok for all chips")
                
            elif (wrong == False):
#                    print ("FEMB_CONFIG_BASE--> FE ASIC SPI is OK")
                break
                
        working_chips = []
        for i,j in enumerate(config_list):
            if (j==1):
                working_chips.append(i)
                
        return working_chips
        
    def configFeAsic(self,gain,shape,base,leak,test_cap,test_dac,dac_value,buffer,monitor_ch=None,acdc="dc",monitor_param=None,s16=None, chip=None, chn=None):

        """
        Gain bits      LARASIC7          LARASIC8
        00                4.7               14
        10                7.8               25
        01                14                7.8
        11                25                4.7 
        """
        if (self.chip_ver == 7):
            if gain == "4.7mV": sg = 0
            elif gain == "7.8mV": sg = 2
            elif gain == "14mV": sg = 1      
            elif gain == "25mV": sg = 3
            else: 
                print("FEMB_CONFIG_BASE--> {} is an invalid gain setting".format(gain))
                return None
        elif (self.chip_ver == 8):
            if gain == "4.7mV": sg = 3
            elif gain == "7.8mV": sg = 1
            elif gain == "14mV": sg = 0       
            elif gain == "25mV": sg = 2
            else:
                print("FEMB_CONFIG_BASE--> {} is an invalid gain setting".format(gain))
                return None
                
        else:
            print("Chip version is {}?".format(self.chip_ver))
            if gain == "4.7mV": sg = 0
            elif gain == "7.8mV": sg = 2
            elif gain == "14mV": sg = 1      
            elif gain == "25mV": sg = 3
            else: 
                print("FEMB_CONFIG_BASE--> {} is an invalid gain setting".format(gain))
                return None
                
        if shape == "0.5us": st = 2
        elif shape == "1us": st = 0
        elif shape == "2us": st = 3        
        elif shape == "3us": st = 1
        else:
            print("FEMB_CONFIG_BASE--> {} is an invalid shaping time setting".format(shape))
            return None

        if leak == "100pA": slk,slkh = 0,1
        elif leak == "500pA": slk,slkh = 0,0
        elif leak == "1nA": slk,slkh = 1,1       
        elif leak == "5nA": slk,slkh = 1,0
        else:
            print("FEMB_CONFIG_BASE--> {} is an invalid leakage current setting".format(leak))
            return None
        
        if test_dac == "test_off": sdacsw1,sdacsw2 = 0,0
        elif test_dac == "test_int": sdacsw1,sdacsw2 = 0,1
        elif test_dac == "test_ext": sdacsw1,sdacsw2 = 1,0
        elif test_dac == "test_meas": sdacsw1,sdacsw2 = 1,1
        else:
            print("FEMB_CONFIG_BASE--> {} is an invalid test pulse/DAC setting".format(test_dac))
            return None
        
        if (test_cap == "on"):
            sts = 1
        elif (test_cap == "off"):
            sts = 0
        else:
            print("FEMB_CONFIG_BASE--> {} is an invalid test capacitor setting".format(test_cap))
            return None
            
        if (base == "200mV"):
            snc = 1
        elif (base == "900mV"):
            snc = 0
        else:
            print("FEMB_CONFIG_BASE--> {} is an invalid baseline setting".format(base))
            return None
            
        if (buffer == "on"):
            sbf = 1
        elif (buffer == "off"):
            sbf = 0
        else:
            print("FEMB_CONFIG_BASE--> {} is an invalid buffer setting".format(buffer))
            return None
            
        sdac = int(dac_value)
        if ((sdac < 0) or (sdac > 32)):
            print("FEMB_CONFIG_BASE--> {} is an invalid internal DAC setting".format(sdac))
            return None
          
        if ((monitor_ch == None) or (monitor_ch == "None") or (monitor_ch == "off")):
            smn = 0
        elif (acdc == "on"):
            smn = 1
        else:
            print("FEMB_CONFIG_BASE--> {} is an invalid channel monitor setting".format(monitor_ch))
            return None
            
        if ((smn == 1) and (sdacsw2 == 1)):
            print("FEMB_CONFIG_BASE--> You're trying to turn on the monitor and SDACSW2!  Read the manual on why you shouldn't!  Turning the monitor off")
            smn = 0
            
        if (acdc == "dc"):
            sdc = 0
        elif (acdc == "ac"):
            sdc = 1
        else:
            print("FEMB_CONFIG_BASE--> {} is an invalid ac/dc setting".format(acdc))
            return None
            
        if ((monitor_param == None) or (monitor_param == "None") or (monitor_param == "off")): stb = 0
        elif monitor_param == "temp": stb = 2
        elif monitor_param == "bandgap": stb = 3
        else:
            print("FEMB_CONFIG_BASE--> {} is an invalid parameter monitoring setting".format(monitor_param))
            return None
            
        if ((s16 == None) or (s16 == "None") or (s16 == "off")):
            s16 = 0
        elif (acdc == "on"):
            s16 = 1
        else:
            print("FEMB_CONFIG_BASE--> {} is an invalid Channel 16 filter setting".format(s16))
            return None
            
        if (chn != None):
            self.feasic_regs = self.set_fe_chn(chip, chn, sts=sts, snc=snc, sg=sg, st=st, smn=smn, sbf=sbf)
        else:
            self.feasic_regs = self.FE_Regs.set_fe_board(sts=sts, snc=snc, sg=sg, st=st, smn=0, sbf=sbf, 
                       slk = slk, stb = stb, s16=s16, slkh=slkh, sdc=sdc, sdacsw2=sdacsw2, sdacsw1=sdacsw1, sdac=sdac)