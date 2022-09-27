from osc_connection import connect
from user_interface import gui_main
from DAQ_control import DAQ
import sys
from time import sleep

# connect to osc
instr = connect()
DAQ().DAQconnect()
sleep(1)

try:
    gui_main(instr)
except KeyboardInterrupt or SystemExit:
    instr.close()  # close osc connection
    DAQ().daq_disconnect()
    sys.exit()

# Limitations in this code :
# - Unable to manually select oscilloscope waveform/point collection rate  (Can only do Auto, max waveform or max points)
# - Voltage response rate limited by speed of code/oscilloscope response. Perhaps multithreading would be beneficial, however code is only ~0.15 sec compared to the 0.2-1.3 sec for the oscilloscope
# - Faster osc. speed means less data points (speed of data transfer -> size of data)
# - Change Pos button is not really necessary right now. If able to get a controllable scan generator, or want to add in capabilities for the oscilloscope to center the peaks, this would allow the user to override any changes in pos by the oscilloscope.
# - Found that the centering was not very important given that ideally one HeNe FSR should be about the scan range
# - Number of points returned by oscilloscope changes depending on scale. This is okay as long as the calibration is done when the oscilloscope returns 3000 points (in code). This could be adjusted by adding other variables that can act as proportionality ratios to keep the calibration
# - Found it was easier to change the scan frequency to fit the scale instead, as that allows for finer tuning than the possible oscilloscope scale values.
