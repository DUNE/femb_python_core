#!/usr/bin/env python33

"""
Configuration for P1 ADC quad-chip board. Note that the fourth socket doesn't
have full external clock functionality because the FPGA ran out of PLLs.
"""

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from builtins import super
from builtins import int
from builtins import range
from builtins import hex
from builtins import str
from future import standard_library
standard_library.install_aliases()
from builtins import object
import sys 
import string
import time
import copy
import os.path
import subprocess
from femb_python.femb_udp import FEMB_UDP
from femb_python.configuration.config_base import FEMB_CONFIG_BASE, FEMBConfigError, SyncADCError, InitBoardError, ConfigADCError, ReadRegError
from femb_python.configuration.adc_asic_reg_mapping_P1_singleADC import ADC_ASIC_REG_MAPPING
from femb_python.test_instrument_interface.keysight_33600A import Keysight_33600A

class FEMB_CONFIG(FEMB_CONFIG_BASE):

    def __init__(self,exitOnError=True):
        super().__init__(exitOnError=exitOnError)
        #declare board specific registers
        self.FEMB_VER = "adctestP1quad"

        self.REG_RESET = 0 # bit 0 system, 1 reg, 2 alg, 3 udp
        self.REG_PWR_CTRL = 1  # bit 0-3 pwr, 8-15 blue LEDs near buttons
        self.REG_ASIC_SPIPROG_RESET = 2 # bit 0 FE SPI, 1 ADC SPI, 4 FE ASIC RESET, 5 ADC ASIC RESET, 6 SOFT ADC RESET & SPI status of some kind
        self.REG_SEL_CH = 3 # bit 0-7 chip, 8-15 channel, 31 WIB mode

        self.REG_DAC1 = 4 # bit 0-15 DAC val, 16-19 tp mode select, 31 set dac
        self.REG_DAC2 = 5 # bit 0-15 tp period, 16-31 tp shift

        self.REG_ADC_TST_PATT = 6 # bit 0-11 tst patt, 16 enable
        self.REG_ADC_CLK = 7 # bit 0-3 clk phase, 8 clk speed sel
        self.REG_LATCHLOC = 8 # bit 0-7 ADC1, 8-15 ADC2, 16-23 ADC3, 24-31 ADC4

        self.REG_STOP_ADC = 9 # header check + busy check
        
        self.REG_LATCHLOC_data_2MHz = 0x0
        self.REG_LATCHLOC_data_1MHz = 0x0
        self.REG_LATCHLOC_data_2MHz_cold = 0x0
        self.REG_LATCHLOC_data_1MHz_cold = 0x0

        self.REG_CLKPHASE_data_2MHz = 0x0
        self.REG_CLKPHASE_data_1MHz = 0x0
        self.REG_CLKPHASE_data_2MHz_cold = 0x0
        self.REG_CLKPHASE_data_1MHz_cold = 0x0

        self.ADC_TESTPATTERN = [0x12, 0x345, 0x678, 0xf1f, 0xad, 0xc01, 0x234, 0x567, 0x89d, 0xeca, 0xff0, 0x123, 0x456, 0x789, 0xabc, 0xdef]

        self.REG_FESPI_BASE = 84
        self.REG_ADCSPI_BASES = [64,69,74,79]
        self.REG_FESPI_RDBACK_BASE = 0x278 # 632 in decimal
        self.REG_ADCSPI_RDBACK_BASE = 0x228 # 552 in decimal

        self.REG_EXTCLK_START = 10
        self.FPGA_FREQ_MHZ = 200 # frequency of FPGA clock in MHz

        self.NASICS = 3
        self.FUNCGENINTER = Keysight_33600A("/dev/usbtmc1",1)
        self.F2DEFAULT = 0
        self.CLKDEFAULT = "fifo"

        self.SAMPLERATE = 2e6

        #initialize FEMB UDP object
        self.femb = FEMB_UDP()

        self.adc_regs = []
        for i in range(self.NASICS):
            self.adc_regs.append(ADC_ASIC_REG_MAPPING())

    def resetBoard(self):
        #Reset system
        self.femb.write_reg( self.REG_RESET, 1)
        time.sleep(5.)

        #Reset registers
        self.femb.write_reg( self.REG_RESET, 2)
        time.sleep(1.)

    def initBoard(self):
        self.turnOnAsics()

        nRetries = 5
        for iRetry in range(nRetries):
            #set up default registers

            #Reset ASICs
            self.femb.write_reg( self.REG_ASIC_SPIPROG_RESET, 1 << 4) # reset FE
            self.femb.write_reg( self.REG_ASIC_SPIPROG_RESET, 1 << 5) # reset ADC
            time.sleep(0.5)

            # test readback
            time.sleep(5.)
            readback = self.femb.read_reg(1)
            if readback is None:
                if self.exitOnError:
                    print("FEMB_CONFIG: Error reading register 0, Exiting.")
                    sys.exit(1)
                else:
                    raise ReadRegError("Couldn't read register 0")

            #Set ADC test pattern register
            self.femb.write_reg( 3, 12) # test pattern off
            #self.femb.write_reg( 3, 12+(1 << 16)) # test pattern on

            #Set ADC latch_loc and clock phase and sample rate
            if self.SAMPLERATE == 1e6:
                if self.COLD:
                    self.femb.write_reg( self.REG_LATCHLOC, self.REG_LATCHLOC_data_1MHz_cold)
                    self.femb.write_reg( self.REG_ADC_CLK, (self.REG_CLKPHASE_data_1MHz_cold & 0xF))
                else:
                    self.femb.write_reg( self.REG_LATCHLOC, self.REG_LATCHLOC_data_1MHz)
                    self.femb.write_reg( self.REG_ADC_CLK, (self.REG_CLKPHASE_data_1MHz & 0xF))
            else: # use 2 MHz values
                if self.COLD:
                    self.femb.write_reg( self.REG_LATCHLOC, self.REG_LATCHLOC_data_2MHz_cold)
                    self.femb.write_reg( self.REG_ADC_CLK, (self.REG_CLKPHASE_data_2MHz_cold & 0xF) + (1 << 8))
                else:
                    self.femb.write_reg( self.REG_LATCHLOC, self.REG_LATCHLOC_data_2MHz)
                    self.femb.write_reg( self.REG_ADC_CLK, (self.REG_CLKPHASE_data_2MHz & 0xF + (1 << 8)))

#            #internal test pulser control
#            self.femb.write_reg( 5, 0x00000000)
#            self.femb.write_reg( 13, 0x0) #enable

            #Set test and readout mode register
            self.femb.write_reg( self.REG_SEL_CH, 1 << 31) # WIB readout mode

#            #Set number events per header
#            self.femb.write_reg( 8, 0x0)

            print("SPI Status:          {:#010x}".format(self.femb.read_reg(2)))
            print("Header & Busy Check: {:#010x}".format(self.femb.read_reg(9)))

            #Configure ADC (and external clock inside)
            try:
                self.configAdcAsic()
                #self.configAdcAsic(clockMonostable=True)
            except ReadRegError:
                continue

            #self.femb.write_reg(self.REG_STOP_ADC,1)
            print("SPI Status:          {:#010x}".format(self.femb.read_reg(2)))
            print("Header & Busy Check: {:#010x}".format(self.femb.read_reg(9)))

#            # Check that board streams data
#            data = self.femb.get_data(1)
#            if data == None:
#                print("Board not streaming data, retrying initialization...")
#                continue # try initializing again
            print("FEMB_CONFIG--> Reset FEMB is DONE")
            return
        print("Error: Board not streaming data after trying to initialize {} times.".format(nRetries))
        if self.exitOnError:
            print("Exiting.")
            sys.exit(1)
        else:
            raise InitBoardError

    def configAdcAsic_regs(self,Adcasic_regs):
        """
        Takes a list NASICS long, each a list of 5 32 bit registers.
        """
        #ADC ASIC SPI registers
        assert(type(Adcasic_regs)==list)
        assert(len(Adcasic_regs)==self.NASICS)
        for k in range(10):
            print("FEMB_CONFIG--> Config ADC ASIC SPI")
            for iChip, chipRegs in enumerate(Adcasic_regs):
                assert(len(chipRegs)==5)
                for iReg in range(5):
                    self.femb.write_reg(self.REG_ADCSPI_BASES[iChip]+iReg, chipRegs[iReg])
                    time.sleep(0.05)

            self.writeSPItoASICS()

            ##enable streaming
            ##self.femb.write_reg( 9, 0x1)

            ##LBNE_ADC_MODE
            ##self.femb.write_reg( 18, 0x1)

            print("FEMB_CONFIG--> Check ADC ASIC SPI")
            adcasic_rb_regs = []
            adcasic_wr_regs = []
            for iChip, chipRegs in enumerate(Adcasic_regs):
                for iReg in range(5):
                    val = self.femb.read_reg(self.REG_ADCSPI_BASES[iChip]+iReg) 
                    if val is None:
                        message = "Error in FEMB_CONFIG.configAdcAsic_regs: read from board failed"
                        print(message)
                        if self.exitOnError:
                            return
                        else:
                            raise ReadRegError
                    adcasic_rb_regs.append(val)
                    adcasic_wr_regs.append(chipRegs[iReg])

            readbackMatch = True
            print("{:32}  {:32}".format("Write","Readback"))
            #print("{:8}  {:8}".format("Write","Readback"))
            for rb, wr in zip(adcasic_rb_regs,adcasic_wr_regs):
                if rb != wr:
                    readbackMatch = False
                print("{:032b}  {:032b}".format(wr,rb))
                #print("{:08X}  {:08X}".format(wr,rb))

            if readbackMatch:
                print("FEMB_CONFIG--> ADC ASIC SPI is OK")
                return
            else: 
                print("FEMB_CONFIG--> ADC ASIC Readback didn't match, retrying...")

        print("Error: Wrong ADC SPI readback.")
        if self.exitOnError:
            print("Exiting.")
            sys.exit(1)
        else:
            raise ConfigADCError

    def configAdcAsic(self,enableOffsetCurrent=None,offsetCurrent=None,testInput=None,
                            freqInternal=None,sleep=None,pdsr=None,pcsr=None,
                            clockMonostable=None,clockExternal=None,clockFromFIFO=None,
                            sLSB=None,f0=None,f1=None,f2=None,f3=None,f4=None,f5=None):
        """
        Configure ADCs
          enableOffsetCurrent: 0 disable offset current, 1 enable offset current
          offsetCurrent: 0-15, amount of current to draw from sample and hold
          testInput: 0 digitize normal input, 1 digitize test input
          freqInternal: internal clock frequency: 0 1MHz, 1 2MHz
          sleep: 0 disable sleep mode, 1 enable sleep mode
          pdsr: if pcsr=0: 0 PD is low, 1 PD is high
          pcsr: 0 power down controlled by pdsr, 1 power down controlled externally
          Only one of these can be enabled:
            clockMonostable: True ADC uses monostable clock
            clockExternal: True ADC uses external clock
            clockFromFIFO: True ADC uses digital generator FIFO clock
          sLSB: LSB current steering mode. 0 for full, 1 for partial (ADC7 P1)
          f0, f1, f2, f3, f4, f5: version specific
        """
        FEMB_CONFIG_BASE.configAdcAsic(self,clockMonostable=clockMonostable,
                                        clockExternal=clockExternal,clockFromFIFO=clockFromFIFO)
        if enableOffsetCurrent is None:
            enableOffsetCurrent=0
        if offsetCurrent is None:
            offsetCurrent=0
        else:
            offsetCurrent = int("{:04b}".format(offsetCurrent)[::-1],2) # need to reverse bits, use string/list tricks
        if testInput is None:
            testInput=1
        if freqInternal is None:
            freqInternal=1
        if sleep is None:
            sleep=0
        if pdsr is None:
            pdsr=0
        if pcsr is None:
            pcsr=0
        if sLSB is None:
            sLSB = 0
        if f1 is None:
            f1 = 0
        if f2 is None:
            f2 = 0
        if f3 is None:
            f3 = 0
        if f4 is None:
            f4 = 1
        if f5 is None:
            f5 = 0
        if not (clockMonostable or clockExternal or clockFromFIFO):
            clockExternal=True
        # a bunch of things depend on the clock choice
        clk0=0
        clk1=0
        if clockExternal:
            clk0=1
            clk1=0
        elif clockFromFIFO:
            clk0=0
            clk1=1
        if f0 is None:
            if clockExternal:
                f0 = 1
            else:
                f0 = 0
        if clockExternal:
            self.extClock(enable=True)
        else:
            self.extClock(enable=False)

        regsListOfLists = []
        for chipRegConfig in self.adc_regs:
            chipRegConfig.set_chip(en_gr=enableOffsetCurrent,d=offsetCurrent,tstin=testInput,frqc=freqInternal,slp=sleep,pdsr=pdsr,pcsr=pcsr,clk0=clk0,clk1=clk1,f0=f0,f1=f1,f2=f2,f3=f3,f4=f4,f5=f5,slsb=sLSB)
            regsListOfLists.append(chipRegConfig.REGS)
        self.configAdcAsic_regs(regsListOfLists)

    def selectChannel(self,asic,chan,hsmode=1):
        """
        asic is chip number 0 to 7
        chan is channel within asic from 0 to 15
        hsmode: if 0 then WIB streaming mode, if 1 only the selected channel. defaults to 1
        """
        hsmodeVal = int(hsmode) & 1 # only 1 bit
        asicVal = int(asic)
        if (asicVal < 0 ) or (asicVal >= self.NASICS ) :
                print( "femb_config_femb : selectChan - invalid ASIC number, only 0 to {} allowed".format(self.NASICS-1))
                return
        chVal = int(chan)
        if (chVal < 0 ) or (chVal > 15 ) :
                print("femb_config_femb : selectChan - invalid channel number, only 0 to 15 allowed")
                return

        #print( "Selecting ASIC " + str(asicVal) + ", channel " + str(chVal))

        regVal = asicVal + (chVal << 8 ) + (hsmodeVal << 31)
        self.femb.write_reg( self.REG_SEL_CH, regVal)

    def syncADC(self):
        #turn on ADC test mode
        print("FEMB_CONFIG--> Start sync ADC")

        originalTestPatternReg = self.femb.read_reg (self.REG_ADC_TST_PATT)
        newReg = ( originalTestPatternReg | (1 << 16) )
        self.femb.write_reg(self.REG_ADC_TST_PATT,newReg) # - enable ADC test pattern
        time.sleep(0.1)                

        alreadySynced = True
        for a in range(0,self.NASICS,1):
            print("FEMB_CONFIG--> Test ADC " + str(a))
            unsync = self.testUnsync(a)
            if unsync != 0:
                alreadySynced = False
                print("FEMB_CONFIG--> ADC not synced, try to fix")
                self.fixUnsync(a)
        latchloc = None
        phase = None
        latchloc = self.femb.read_reg ( self.REG_LATCHLOC ) 
        clkphase = self.femb.read_reg ( self.REG_ADC_CLK ) & 0x1111
        if self.SAMPLERATE == 1e6:
            if self.COLD:
                self.REG_LATCHLOC_data_1MHz_cold = latchloc
                self.REG_CLKPHASE_data_1MHz_cold = clkphase
            else:
                self.REG_LATCHLOC_data_1MHz = latchloc
                self.REG_CLKPHASE_data_1MHz = clkphase
        else: # 2 MHz
            if self.COLD:
                self.REG_LATCHLOC_data_2MHZ_cold = latchloc
                self.REG_CLKPHASE_data_2MHZ_cold = clkphase
            else:
                self.REG_LATCHLOC_data_2MHZ = latchloc
                self.REG_CLKPHASE_data_2MHZ = clkphase
        print("FEMB_CONFIG--> Latch latency {:#010x} Phase: {:#010x}".format(
                        latchloc, clkphase))
        self.femb.write_reg ( self.REG_ADC_TST_PATT, originalTestPatternReg )
        self.femb.write_reg ( self.REG_ADC_TST_PATT, originalTestPatternReg )
        print("FEMB_CONFIG--> End sync ADC")
        return not alreadySynced,latchloc,clkphase

    def testUnsync(self, adc):
        print("Starting testUnsync adc: ",adc)
        adcNum = int(adc)
        if (adcNum < 0 ) or (adcNum > 7 ):
                print("FEMB_CONFIG--> femb_config_femb : testLink - invalid asic number")
                return
        
        #loop through channels, check test pattern against data
        badSync = 0
        for ch in range(0,16,1):
                self.selectChannel(adcNum,ch, 1)
                time.sleep(0.05)                
                for test in range(0,10,1):
                        data = self.femb.get_data(1)
                        #print("test: ",test," data: ",data)
                        if data == None:
                                continue
                        for samp in data[0:(16*1024+1023)]:
                                if samp == None:
                                        continue
                                chNum = ((samp >> 12 ) & 0xF)
                                sampVal = (samp & 0xFFF)
                                if sampVal != self.ADC_TESTPATTERN[ch]        :
                                        badSync = 1 
                                if badSync == 1:
                                        break
                        if badSync == 1:
                                break
                if badSync == 1:
                        break
        return badSync


    def fixUnsync(self, adc):
        adcNum = int(adc)
        if (adcNum < 0 ) or (adcNum > 7 ):
                print("FEMB_CONFIG--> femb_config_femb : testLink - invalid asic number")
                return

        initLATCH = self.femb.read_reg ( self.REG_LATCHLOC )
        initPHASE = self.femb.read_reg ( self.REG_ADC_CLK ) # remember bit 16 sample rate

        #phases = [0,1,0,1,0]
        phases = [0,1]

        #loop through sync parameters
        for shift in range(0,16,1):
            shiftMask = (0xFF << 8*adcNum)
            testShift = ( (initLATCH1_4 & ~(shiftMask)) | (shift << 8*adcNum) )
            self.femb.write_reg ( self.REG_LATCHLOC, testShift )
            time.sleep(0.01)
            for phase in phases:
                clkMask = (0x1 << adcNum)
                testPhase = ( (initPHASE & ~(clkMask)) | (phase << adcNum) ) 
                self.femb.write_reg ( self.REG_ADC_CLK, testPhase )
                time.sleep(0.01)
                print("try shift: {} phase: {} testingUnsync...".format(shift,phase))
                #reset ADC ASIC
                self.femb.write_reg ( self.REG_ASIC_SPIPROG_RESET, 1 << 5) # reset ADC
                time.sleep(0.01)
                self.femb.write_reg ( self.REG_ASIC_SPIPROG_RESET, 1 << 1) # prog ADC SPI
                time.sleep(0.01)
                self.femb.write_reg ( self.REG_ASIC_SPIPROG_RESET, 1 << 1) # prog ADC SPI
                time.sleep(0.01)
                #test link
                unsync = self.testUnsync(adcNum)
                if unsync == 0 :
                    print("FEMB_CONFIG--> ADC synchronized")
                    return
        #if program reaches here, sync has failed
        print("Error: FEMB_CONFIG--> ADC SYNC process failed for ADC # " + str(adc))
        print("Setting back to original values: LATCHLOC: {:#010x}, PHASE: {:#010x}".format,initLATCH,initPHASE & 0xF)
        self.femb.write_reg ( self.REG_LATCHLOC, initLATCH )
        self.femb.write_reg ( self.REG_ADC_CLK, initPHASE )
        if self.exitOnError:
            sys.exit(1)
        else:
            raise SyncADCError

    def extClock(self, enable=False, 
                period=500, mult=1, 
                offset_rst=0, offset_read=480, offset_msb=230, offset_lsb=480,
                width_rst=50, width_read=20, width_msb=270, width_lsb=20,
                offset_lsb_1st_1=50, width_lsb_1st_1=190,
                offset_lsb_1st_2=480, width_lsb_1st_2=20,
                inv_rst=True, inv_read=True, inv_msb=False, inv_lsb=False, inv_lsb_1st=False):
        """
        Programs external clock. All non-boolean arguments except mult are in nanoseconds
        IDXM = msb
        IDXL = lsb
        IDL = lsb_1st
        """

        rd_en_off = 0
        adc_off = 0
        adc_wid = 0
        msb_off = 0
        msb_wid = 0
        period_val = 0
        lsb_fc_wid2 = 0
        lsb_fc_off1 = 0
        rd_en_wid = 0
        lsb_fc_wid1 = 0
        lsb_fc_off2 = 0
        lsb_s_wid = 0
        lsb_s_off = 0
        inv = 0

        if enable:
            clock = 1./self.FPGA_FREQ_MHZ * 1000. # clock now in ns
            print("FPGA Clock freq: {} MHz period: {} ns".format(self.FPGA_FREQ_MHZ,clock))
            print("ExtClock option mult: {}".format(mult))
            print("ExtClock option period: {} ns".format(period))
            print("ExtClock option offset_read: {} ns".format(offset_read))
            print("ExtClock option offset_rst: {} ns".format(offset_rst))
            print("ExtClock option offset_msb: {} ns".format(offset_msb))
            print("ExtClock option offset_lsb: {} ns".format(offset_lsb))
            print("ExtClock option offset_lsb_1st_1: {} ns".format(offset_lsb_1st_1))
            print("ExtClock option offset_lsb_1st_2: {} ns".format(offset_lsb_1st_2))
            print("ExtClock option width_read: {} ns".format(width_read))
            print("ExtClock option width_rst: {} ns".format(width_rst))
            print("ExtClock option width_msb: {} ns".format(width_msb))
            print("ExtClock option width_lsb: {} ns".format(width_lsb))
            print("ExtClock option width_lsb_1st_1: {} ns".format(width_lsb_1st_1))
            print("ExtClock option width_lsb_1st_2: {} ns".format(width_lsb_1st_2))
            print("ExtClock option inv_rst: {}".format(inv_rst))
            print("ExtClock option inv_read: {}".format(inv_read))
            print("ExtClock option inv_msb: {}".format(inv_msb))
            print("ExtClock option inv_lsb: {}".format(inv_lsb))
            print("ExtClock option inv_lsb_1st: {}".format(inv_lsb_1st))
            denominator = clock/mult
            print("ExtClock denominator: {} ns".format(denominator))
            period_val = period // denominator
            print("ExtClock period: {} ns".format(period_val))

            rd_off      = int(offset_read // denominator) & 0xFFFF
            rst_off     = int(offset_rst // denominator) & 0xFFFF
            rst_wid     = int(width_rst // denominator) & 0xFFFF
            msb_off     = int(offset_msb // denominator) & 0xFFFF
            msb_wid     = int(width_msb // denominator) & 0xFFFF
            lsb_fc_wid2 = int(width_lsb_1st_2 // denominator) & 0xFFFF
            lsb_fc_off1 = int(offset_lsb_1st_1 // denominator) & 0xFFFF
            rd_wid      = int(width_read // denominator) & 0xFFFF
            lsb_fc_wid1 = int(width_lsb_1st_1 // denominator) & 0xFFFF
            lsb_fc_off2 = int(offset_lsb_1st_2 // denominator) & 0xFFFF
            lsb_wid     = int(width_lsb // denominator) & 0xFFFF
            lsb_off     = int(offset_lsb // denominator) & 0xFFFF

            if inv_rst:
              inv += 1 << 0
            if inv_read:
              inv += 1 << 1
            if inv_msb:
              inv += 1 << 2
            if inv_lsb:
              inv += 1 << 3
            if inv_lsb_1st:
              inv += 1 << 4

        regsValsToWrite = [
            ("inv", inv),
        ]
        for i in range(3): # NASICs with ext clock
            iStr = str(i)
            asicRegs = [
                ("RST_ADC"+iStr,(rst_wid << 16) | rst_off),
                ("READ_ADC"+iStr,(rd_wid << 16) | rd_off),
                ("IDXM_ADC"+iStr,(msb_wid << 16) | msb_off), # msb
                ("IDXL_ADC"+iStr,(lsb_wid << 16) | lsb_off), # lsb
                ("IDL1_ADC"+iStr,(lsb_fc_wid1 << 16) | lsb_fc_off1), # lsb_fc_1
                ("IDL2_ADC"+iStr,(lsb_fc_wid2 << 16) | lsb_fc_off2), # lsb_fc_1
                ("pll_STEP0_ADC"+iStr,0),
                ("pll_STEP1_ADC"+iStr,0),
                ("pll_STEP2_ADC"+iStr,0),
            ]
            regsValsToWrite += asicRegs

        for iReg, tup in enumerate(regsValsToWrite):
            name = tup[0]
            val = tup[1]
            reg = iReg + self.REG_EXTCLK_START
            print("ExtClock Register {0:15} number {1:3} set to {2:10} = {2:#010x}".format(name,reg,val))
            #print("ExtClock Register {0:15} number {1:3} set to {2:#034b}".format(name,reg,val))
            self.femb.write_reg(iReg,val)

    def writeSPItoASICS(self):
        self.femb.write_reg(self.REG_ASIC_SPIPROG_RESET,0)
        self.femb.write_reg(self.REG_ASIC_SPIPROG_RESET,3)
        time.sleep(0.1)
        self.femb.write_reg(self.REG_ASIC_SPIPROG_RESET,2)
        time.sleep(0.1)
        self.femb.write_reg(self.REG_ASIC_SPIPROG_RESET,0)

        #time.sleep(0.5)
        #syncVar = self.femb.read_reg(self.REG_ASIC_SPIPROG_RESET)
        #if syncVar is None:
        #    print("FEMB_CONFIG--> Result of writing SPI: {:#010x}".format(syncVar))
        #else:
        #    print("FEMB_CONFIG--> Result of writing SPI: None")

    def turnOffAsics(self):
        oldReg = self.femb.read_reg(self.REG_PWR_CTRL)
        newReg = oldReg & 0xFFFFFFF0
        self.femb.write_reg( self.REG_PWR_CTRL, newReg)
        #pause after turning off ASICs
        time.sleep(2)
        #self.femb.write_reg(self.REG_RESET, 4) # bit 2 is ASIC reset as far as I can see

    def turnOnAsic(self,asic):
        asicVal = int(asic)
        if (asicVal < 0 ) or (asicVal >= self.NASICS ) :
                print( "femb_config_femb : turnOnAsics - invalid ASIC number, only 0 to {} allowed".format(self.NASICS-1))
                return
        print( "turnOnAsic " + str(asicVal) )
        oldReg = self.femb.read_reg(self.REG_PWR_CTRL)
        newReg = oldReg | (1 << asic)
        self.femb.write_reg( self.REG_PWR_CTRL , newReg)

        time.sleep(2) #pause after turn on
        #self.femb.write_reg(self.REG_RESET, 4) # bit 2 is ASIC reset as far as I can see

    def turnOnAsics(self):
        print( "turnOnAsics 0-{}".format(int(self.NASICS -1)))

        oldReg = self.femb.read_reg(self.REG_PWR_CTRL)
        newReg = oldReg | int(2**self.NASICS - 1)
        self.femb.write_reg( self.REG_PWR_CTRL, newReg)

        #pause after turning on ASICs
        time.sleep(5)
        #self.femb.write_reg(self.REG_RESET, 4) # bit 2 is ASIC reset as far as I can see
