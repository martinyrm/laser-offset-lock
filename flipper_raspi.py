import numpy as np
import socket
import time
from DAQ_control import DAQ

UDP_IP = "isyspi03"  # set it to destination IP. RPi in this case
UDP_PORT = 25566
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


# code on rasp pi for pin __
# responds to flipper=1 (up, 5V) (actually 3.3V) and flipper=0 (down, 0V )

class PeakIdentification:
    """Required functions to identify the HeNe peak from two peaks on oscilloscope display"""
    def __init__(self, ident_peaks=None, peaks_loc=None, peaks_identified=None):
        self.ident_peaks = ident_peaks
        self.peaks_loc = peaks_loc
        self.peaks_identified = peaks_identified

    def peak_identity(self, stage, prev_peaks, mirror_up, mirror_error):
        """identifies the HeNe peak by flipping the mirror and finding the peak of the pair closest to the single peak when the mirror is up. Requires all parameters in init to be filled."""
        print("stage:", stage)
        HeNe_closest = None
        if stage == 0:
            prev_peaks = self.peaks_loc
        elif stage == 1:
            FlipperControl.flipper_on()
            mirror_up = True
        elif stage == 5:
            try:
                if len(self.peaks_loc) != 1:
                    raise ValueError
                single_peak = self.peaks_loc
                HeNe_closest = prev_peaks[self.find_closest(single_peak, prev_peaks)]
                FlipperControl.flipper_off()
                mirror_up = False
                self.peaks_identified = True
                stage = -1
                self.ident_peaks = False
            except ValueError:
                FlipperControl.flipper_off()
                mirror_up = False
                self.peaks_identified = False
                mirror_error = True
                stage = -1
                self.ident_peaks = False
        stage += 1
        if mirror_up:
            loc_mirror = 1
        else:
            loc_mirror = 0
        return self.peaks_identified, stage, prev_peaks, HeNe_closest, mirror_up, self.ident_peaks, loc_mirror, mirror_error

    @staticmethod
    def find_closest(single_peak, list_peaks):
        """Returns index of the closest value in list"""
        try:
            peak_closest = (np.abs(list_peaks - single_peak)).argmin()
        except (ValueError, IndexError):
            peak_closest = None
        return peak_closest


    def check_peaks_in_range(self, hene_peak, change_pos, waveform):
        """Requires all parameters in init to be filled."""
        try:
            if abs(hene_peak - self.peaks_loc[self.find_closest(hene_peak, self.peaks_loc)]) >= (
                    self.peaks_loc[1] - self.peaks_loc[0]) / 2 and not change_pos and self.peaks_identified:
                self.ident_peaks = True
            if (len(waveform) - hene_peak) <= 50 or hene_peak <= 50:
                self.peaks_identified = False
        except IndexError:
            pass
        return self.ident_peaks, self.peaks_identified


##########################################
# flipper control
#  TODO pop up if  click multiple times to ask if connected to raspi

class FlipperControl:
    @staticmethod
    def flipper_on():
        # to add - led saying if up or down, and any manual input?
        DAQ.daq_mirror_flipper_on()
        sock.sendto(b'flipper=1\n', (UDP_IP, UDP_PORT))
        time.sleep(5)

        print("up")

    @staticmethod
    def flipper_off():
        DAQ.daq_mirror_flipper_off()
        sock.sendto(b'flipper=0\n', (UDP_IP, UDP_PORT))
        time.sleep(5)

        print("down")
