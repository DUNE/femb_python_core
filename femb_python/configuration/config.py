"""
Main Configuration module.
"""
import sys
import os.path
import time
from .config_file_parser import CONFIG_FILE
from .asic_reg_packing import ASIC_REG_PACKING
from .fe_asic_config import FE_CONFIG
from ..femb_udp import FEMB_UDP

class CONFIG:
    """
    Main configuration class. Rangles other classes that configure the ADC ASIC and FE ASIC.
    """

    def resetBoard(self):
      #Reset system
      self.femb.write_reg( self.REG_RESET, 1)
      time.sleep(5.)

      #Reset registers
      self.femb.write_reg( self.REG_RESET, 2)
      time.sleep(1.)

      if self.fe:
        #Reset FE ASICs
        self.femb.write_reg( self.REG_ASIC_RESET, 2)
        time.sleep(0.5)
      if self.adc:
        #Reset ADC ASICs
        self.femb.write_reg( self.REG_ASIC_RESET, 1)
        time.sleep(0.5)

    def initBoard(self):
      self.resetBoard()
      self.setRegisterInitialVals()
      if self.TOGGLE_HSLINK:
        self.femb.write_reg( self.REG_HSLINK, 0x1)
        self.femb.write_reg( self.REG_HSLINK, 0x0)
      if self.fe:
        self.fe.configureDefault()
      if self.adc:
        self.configAdcAsic()

    def configFeAsic(self,gain,shape,base):
      if self.fe:
        self.fe.configFeAsic(gain,shape,base)
      else:
        print("CONFIG.configFeAsic: no FE ASIC present in configuration")

    def configAdcAsic(self,regs=None):
        if not regs: # then get from configuration file
            nbits_global = self.config_file.get("ADC_CONFIGURATION","NBITS_GLOBAL")
            nbits_channel = self.config_file.get("ADC_CONFIGURATION","NBITS_CHANNEL")
            global_bits = self.config_file.get("ADC_CONFIGURATION","GLOBAL_BITS")
            channel_bits = self.config_file.get("ADC_CONFIGURATION","CHANNEL_BITS")
            print(("Setting all ADC global config registers to {:#0"+str(nbits_global+2)+"b}").format(global_bits))
            print(("Setting all ADC channel config registers to {:#0"+str(nbits_channel+2)+"b}").format(channel_bits))
            arp = ASIC_REG_PACKING(nbits_global,nbits_channel)
            arp.set_board(global_bits,channel_bits)
            #arp.set_board(0b00110010,0b00001100)
            #arp.set_chip(0,0b00110101,0b00001101)
            regs = arp.getREGS()
        checkReadback = True
        try:
            checkReadback = not self.DONTCHECKREADBACK
        except:
            pass
        #ADC ASIC SPI registers
        print("CONFIG--> Config ADC ASIC SPI")
        for k in range(10):
            i = 0
            for regNum in range(self.REG_ADCSPI_BASE,self.REG_ADCSPI_BASE+len(regs),1):
                    self.femb.write_reg( regNum, regs[i])
                    i = i + 1

            #Write ADC ASIC SPI
            print("CONFIG--> Program ADC ASIC SPI")
            self.femb.write_reg( self.REG_ASIC_SPIPROG, 1)
            time.sleep(0.1)
            self.femb.write_reg( self.REG_ASIC_SPIPROG, 1)
            time.sleep(0.1)

            print("CONFIG--> Check ADC ASIC SPI")
            adcasic_rb_regs = []
            for regNum in range(self.REG_ADCSPI_RDBACK_BASE,self.REG_ADCSPI_RDBACK_BASE+len(regs),1):
                val = self.femb.read_reg( regNum ) 
                adcasic_rb_regs.append( val )
                print(hex(val))

            if checkReadback:
                if (adcasic_rb_regs !=regs  ) :
                    if ( k == 1 ):
                        sys.exit("CONFIG : Wrong readback. ADC SPI failed")
                        return
                else: 
                    print("CONFIG--> ADC ASIC SPI is OK")
                    break
            else:
                print("CONFIG--> Not checking if ADC readback is okay")
                break

    def selectChannel(self,asic,chan):
        asicVal = int(asic)
        if (asicVal < 0 ) or (asicVal > self.NASICS - 1) :
                print("config_femb : selectChan - invalid ASIC number, must be between 0 and {0}".format(self.NASICS - 1))
                return
        chVal = int(chan)
        if (chVal < 0 ) or (chVal > 15) :
                print("config_femb : selectChan - invalid channel number, must be between 0 and 15")
                return
        #print "Selecting ASIC " + str(asicVal) + ", channel " + str(chVal)
        regVal = (chVal << 8 ) + asicVal
        self.femb.write_reg( self.REG_SEL_CH, regVal)

    def setInternalPulser(self,pulserEnable,pulseHeight):
      if self.fe:
        self.fe.setInternalPulser()
      else:
        print("CONFIG.setInternalPulser: no FE ASIC present in configuration")

    def syncADC(self):
      if self.adc:
        self.adc.syncADC()
      else:
        print("CONFIG.syncADC: no ADC ASIC present in configuration")

    def testUnsync(self, adc):
      if self.adc:
        self.adc.testUnsync(adc)
      else:
        print("CONFIG.syncADC: no ADC ASIC present in configuration")

    def fixUnsync(self, adc):
      if self.adc:
        self.adc.fixUnsync(adc)
      else:
        print("CONFIG.syncADC: no ADC ASIC present in configuration")

    def setRegisterInitialVals(self):
        for key in self.config_file.listKeys("REGISTER_INITIAL_VALUES"):
          regName = key.upper()
          regLoc = None
          try:
            regLoc = getattr(self,regName)
          except:
            raise Exception("Register Location for '{}' not found in '{}'".format(regLoc,self.filename))
          regVal = self.config_file.get("REGISTER_INITIAL_VALUES",key)
          print("Setting {}, reg {} to {:#010x}".format(regName,regLoc,regVal))
          self.femb.write_reg(regLoc,regVal)

    #__INIT__#
    def __init__(self,config_file_name):
        print("Using configuration file: {}".format(os.path.abspath(config_file_name)))
        #initialize FEMB UDP object
        self.femb = FEMB_UDP()
        #read the config file
        self.filename = config_file_name
        self.config_file = CONFIG_FILE(self.filename)
        self.adc = None
        self.fe = None
        #if self.config_file.hasADC():
        if True:
          #self.adc = ADC_CONFIG(self.config_file,self.femb)
          self.adc = True
        if False:
          self.fe = FE_CONFIG(self.config_file,self.femb)
        for key in self.config_file.listKeys("GENERAL"):
          setattr(self,key.upper(),self.config_file.get("GENERAL",key))
        for key in self.config_file.listKeys("REGISTER_LOCATIONS"):
          setattr(self,key.upper(),self.config_file.get("REGISTER_LOCATIONS",key))
        try:
          setattr(self,"TOGGLE_HSLINK",self.config_file.get("GENERAL","TOGGLE_HSLINK",isBool=True))
        except:
          setattr(self,"TOGGLE_HSLINK",False)
        try:
          setattr(self,"DONTCHECKREADBACK",self.config_file.get("GENERAL","DONTCHECKREADBACK",isBool=True))
        except:
          setattr(self,"DONTCHECKREADBACK",False)
        

if __name__ == "__main__":
    print("########################################")
    print("35t.ini:")
    cfg = CONFIG("35t.ini")
    print("########################################")
    print("adctest.ini:")
    cfg = CONFIG("adctest.ini")
