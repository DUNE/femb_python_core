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

class LOW_LEVEL(object):
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

    def selectChipChannel(self,chip,chn):
        """
        Selects the chip and channel you want read out, doesn't matter if the board is reading out in "WIB mode"
        This method works for the first board to use this framework (Quad FE) so it may need to be adjusted in the future
        """
        if (chip < int(self.config["DEFAULT"]["NASIC_MIN"]) ) or (chip > int(self.config["DEFAULT"]["NASIC_MAX"]) ):
            print ("FEMB_CONFIG_BASE -> Error in selectChipChannel: Chip must be between {} and {}, but it was {}".format(int(self.config["DEFAULT"]["NASIC_MIN"]), int(self.config["DEFAULT"]["NASIC_MAX"]), chip))
            return
            
        if (chn < int(self.config["DEFAULT"]["NASICCH_MIN"]) ) or (chn > int(self.config["DEFAULT"]["NASICCH_MAX"]) ):
            print ("FEMB_CONFIG_BASE -> Error in selectChipChannel: Channel must be between {} and {}, but it was {}".format(int(self.config["DEFAULT"]["NASICCH_MIN"]), int(self.config["DEFAULT"]["NASICCH_MAX"]), chn))
            return
          
        chip_int = int(chip)
        chn_int = int(chn)
        self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_CH_SEL"]), chn_int + (chip_int << 8))

        
    #Get data in a variety of ways.  You can even pre-convert it to mV!
    def get_data_chipXchnX(self, chip, chn, packets = 1, data_format = "counts", header = False):
        
        self.selectChipChannel(chip = chip, chn = chn)
            
        if (data_format == "bin"):
            data = self.femb_udp.get_data_packets(data_type = "bin", num = packets, header = header)

        data = self.femb_udp.get_data_packets(data_type = "int", num = packets, header = header)
        
        if (data_format == "mV"):
            for i in range (len(data)):
                data[i] = data[i] * (float(self.config["DEFAULT"]["ADC_REF_VOLTAGE"]) / int(self.config["DEFAULT"]["ADC_FULL_SCALE"], 16)) / 1000
                
        elif (data_format == "V"):
            for i in range (len(data)):
                data[i] = data[i] * (float(self.config["DEFAULT"]["ADC_REF_VOLTAGE"]) / int(self.config["DEFAULT"]["ADC_FULL_SCALE"], 16))
                
        return data
        
    def get_data_chipXchnX_tagged(self, chip, chn, packets = 1, data_format = "counts", header = False):
        traces = 0
        loops = 0
        data_to_return = []
        while (traces < packets):
            loops = loops + 1
            data = list(self.get_data_chipXchnX(chip, chn, packets = 5, data_format = "counts"), header = header)
            found_trace = False
            for i in range(len(data)):
                #if (data[i] > self.adc_full_scale):
                #Positive pulse
                if (data[i] & (0b10 << 14)):
                    if (len(data[i:]) > int(self.config["SYNC_SETTINGS"]["SYNC_PULSE_SPACING"])):
                        enough_data = True
                    else:
                        enough_data = False
                        break
                    
                    additional_pulse = False
                    for j in range(i+1,i+int(self.config["SYNC_SETTINGS"]["SYNC_PULSE_SPACING"]),1):
                        if (data[j] & (0b10 << 14)):
                            additional_pulse = True
                            break
                        
                    if ((additional_pulse == False) and (enough_data == True)):
                        data[i] = data[i] & int(self.config["DEFAULT"]["ADC_FULL_SCALE"], 16)
                        data_to_send = []
                        data_to_send.extend(list(data[i:i+int(self.config["SYNC_SETTINGS"]["SYNC_PULSE_SPACING"])]))
                        found_trace = True
                        break
            if (found_trace):
                traces = traces + 1
                data_to_return.extend(list(data_to_send))
            if (loops > (packets*10)):
                print("FEMB_CONFIG_BASE--> Channel {}, Not enough traces found".format(chn))
                break
            
        if (data_format == "mV"):
            for i in range (len(data)):
                data[i] = data[i] * (float(self.config["DEFAULT"]["ADC_REF_VOLTAGE"]) / int(self.config["DEFAULT"]["ADC_FULL_SCALE"], 16)) / 1000
                
        elif (data_format == "V"):
            for i in range (len(data)):
                data[i] = data[i] * (float(self.config["DEFAULT"]["ADC_REF_VOLTAGE"]) / int(self.config["DEFAULT"]["ADC_FULL_SCALE"], 16))
            
        return data_to_return
        
    def setInternalPulser(self, period = 0, shift = 0, enable = None):
        if (enable == True):
            en_byte = self.config['DEFINITIONS'].getboolean('INTERNAL_PULSE_ON', 2)
        else:
            en_byte = self.config['DEFINITIONS'].getboolean('INTERNAL_PULSE_OFF')
            
        INTERNAL_VALUE = (period << 16) + (shift << 8) + (en_byte)
        self.femb_udp.write_reg(self.config["REGISTERS"]["REG_INT_PULSE"], INTERNAL_VALUE)
        
    def setExternalPulser(self,val=None,period=None,shift=None,enable=None):
        if (val != None):
            int_val = int(val)
            if ((int_val > 0) or (int_val < int(self.config["DEFAULT"]["EXTERNAL_DAC_VAL_MAX"], 16))):
                self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_EXT_DAC_VAL"]), int_val)
                
                self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_EXT_DAC_SET"]), int(self.config["DEFINITIONS"]["PCB_DAC_STOP"]))
                self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_EXT_DAC_SET"]), int(self.config["DEFINITIONS"]["PCB_DAC_START"]))
                self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_EXT_DAC_SET"]), int(self.config["DEFINITIONS"]["PCB_DAC_STOP"]))
            else:
                print("FEMB_CONFIG_BASE--> External Pulser is trying to set a value of {} (max value is {})".format(int_val, int(self.config["DEFAULT"]["EXTERNAL_DAC_VAL_MAX"], 16)))
                
        if (enable != None):
            if (enable == True):
                self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_EXT_DAC_PWR"]), int(self.config["DEFINITIONS"]["EXT_DAC_ON"]))
            elif (enable == False):
                self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_EXT_DAC_PWR"]), int(self.config["DEFINITIONS"]["EXT_DAC_OFF"], 16))
                
        if ((period!=None) and (shift!=None)):
            self.femb_udp.write_reg(int(self.config["REGISTERS"]["REG_EXT_PULSE"]), (shift << 16) + period)