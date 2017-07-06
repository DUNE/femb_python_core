#!/usr/bin/env python3
'''
This provides a command line interface to the oscillator testing.

It manages a runpolicy object in order to run the osc.  testing script
in a manner consistent with other CE testing stations

It maintains a state over a test sequence.
'''

from femb_python import runpolicy

class Cycle(object):
    def __init__(self, readymsg, finishmsg, **params):
        self._readymsg = readymsg
        self._finishmsg = finishmsg
        self._params = params;
        pass

    def runparams(self):
        '''
        Return parameters that should be passed to a runner's run.
        ''' 
        return self._params


    def _prompt(self, msg, respfunc=None, **params):
        prompt = self._format(msg, **params)
        resp = input(prompt)
        if respfunc:
            return respfunc(resp)
        return

    def get_yes(self, msg, yes="y"):
        '''
        Loop until we get something from user that starts with a 'y'
        '''
        while True:
            res = input(msg)
            if res.lower().startswith(yes):
                return

    def __call__(self, runner):
        '''
        Perform the cycle.
        '''
        params = runner.resolve(**self._params)

        self.get_yes(self._readymsg.format(**params))
        runner(**params)
        self.get_yes(self._finishmsg.format(**params))
        

class Sequencer(object):
    def __init__(self, cycles, runner):
        self.cycles = cycles
        self.runner = runner              # a runpolicy object

    def run(self):
        for cycle in self.cycles:
            cycle(self.runner)


def main(**params):
    '''
    Main entry to the oscillator test script.
    '''

    readymsg = "Start cycle {cycle}.  Are the oscillators cold and ready for testing? (y/n): "
    finishmsg = "Finished cycle {cycle}.  Are the oscillators removed from LN2? (y/n): "

    cycles = [Cycle(readymsg, finishmsg, cycle=n, datasubdir="cycle{cycle}") for n in range(3)]
    r = runpolicy.make_runner("notest",False, executable="/bin/echo", argstr="cycle is {cycle} in {datadir} with {outlabel}", **params)
    s = Sequencer(cycles, r)
    s.run()
    
    
if '__main__' == __name__:
    main(datadisks=["/tmp"])
    
    
