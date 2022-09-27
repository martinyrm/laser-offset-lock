import beepy
import numpy as np
import scipy.signal as signal
# import DAQ_control
from DAQ_control import DAQ
from time import time

old_time = time()


class Signal:
    def __init__(self, pos, default_pos, change_pos, locking, in_MHz, continue_lock, scale, laser_lock_status,
                 peaks_identified, ident_peaks, default_scale, dict_laser_info, laser_name, show_trig_sig, manual_adj_V):
        self.manual_adj_V = manual_adj_V
        self.voltage_out = None
        self.pos = pos
        self.default_pos = default_pos
        self.change_pos = change_pos
        self.locking = locking
        self.in_MHz = in_MHz
        self.continue_lock = continue_lock
        self.scale = scale
        self.laser_lock_status = laser_lock_status
        self.peaks_identified = peaks_identified
        self.ident_peaks = ident_peaks
        self.default_scale = default_scale
        self.dict_laser_info = dict_laser_info
        self.laser_name = laser_name
        self.show_trig_sig = show_trig_sig

    def signal_response(self, num_peaks, separation, rapid_data, correction_array):
        """ Response depending on signal.
             If 2 peaks are observed, laser is controlled to keep frequency lock.
             If < or > 2 peaks are observed, oscilloscope will try to adjust horizontal position to find peaks.
             If no peaks are found, oscilloscope will reset to default pos and scale.
        """
        global old_time
        response_rate = self.dict_laser_info[self.laser_name][4]
        if not rapid_data and response_rate < 1.5:
            response_rate = 1.5
        correction = None
        uncal_sep = separation  # uncalibration separation
        if separation != 0 and self.in_MHz is not None:
            separation = (separation * self.in_MHz)  # separation in MHZ
        lost_peaks = False
        self.laser_lock_status = True
        voltage_out = False
        if not self.change_pos:
            if num_peaks == 2 and self.locking and self.peaks_identified and self.in_MHz is not None:
                # control laser
                correction = lock_laser(separation, self.dict_laser_info, self.laser_name, correction_array, self.manual_adj_V)
                if -5 < correction < 5:
                    self.laser_lock_status = True
                    if (time() - old_time) >= float(response_rate):
                        voltage_out = True
                        DAQ().daq_output(correction)
                        old_time = time()
                else:
                    self.laser_lock_status = False
            elif num_peaks == 2 and not self.locking:
                pass
            elif num_peaks > 2 or num_peaks == 1:
                self.laser_lock_status = False
                if self.locking:
                    beepy.beep(sound=3)
            elif num_peaks == 0:
                if self.locking and not self.continue_lock:
                    lost_peaks = True
                    beepy.beep(sound=3)
                elif self.locking and self.continue_lock:
                    lost_peaks = False
                self.laser_lock_status = False
        else:
            pass
        if not self.laser_lock_status:
            pass
            DAQ().daq_output(0)
        return self.pos, self.laser_lock_status, separation, lost_peaks, self.scale, correction, voltage_out, uncal_sep

    def final_data(self, instr, rapid_data, correction_array):
        waveform, peaks_loc, num_peaks, separation, peaks, trigger_data = get_trace(instr, self.show_trig_sig)
        pos, laser_lock_status, separation, lost_peaks, self.scale, correction, voltage_out, uncal_sep = self.signal_response(
            num_peaks,
            separation, rapid_data, correction_array)
        len_waveform = len(waveform)


        return waveform, peaks_loc, separation, self.pos, num_peaks, self.scale, laser_lock_status, lost_peaks, trigger_data, correction, voltage_out, uncal_sep, len_waveform


def status_indicator(num_peaks, separation, in_MHz):
    # for LED on GUI. True if 2 peaks and not ~3000 MHz apart
    if num_peaks == 2 and in_MHz and not 2980 <= separation <= 3020:
        return True
    else:d
        return False


# TODO when get controllable scan generator
def scan_gen__drift_control(HeNe_peak_loc, FSR, desired_offset):
    """NOT USED/TESTED: Controls scan generator offset to counteract cavity length changes. Could implement automatic start up offset correction"""
    # 5952 is len of waveform data
    pos_peak_leeway = 5  # MHz
    pos_for_HeNe = FSR / 2 + desired_offset + pos_peak_leeway  # put center of  HeNe peak and desired offset at middle of screen, 5 is the
    if pos_for_HeNe >= HeNe_peak_loc or HeNe_peak_loc >= pos_for_HeNe:  # put center between HeNe peak and desired offset at actual center
        # send signal to scan to correct offset
        pass


def lock_laser(separation, dict_laser_info, laser_name, correction_array, manual_adj_V):
    """Convert to MHz, find difference between desired offset and actual offset.
    Assuming that positive voltage = increase in frequency.
    If not, input voltage for 1 MHz as a negative number.
    """
    voltage_1MHz = dict_laser_info[laser_name][3]  # voltage value equivalent to 1MHz change in laser frequency
    desired_offset = dict_laser_info[laser_name][0]  # desired offset from HeNe peak

    if len(correction_array) == 0:
        error = separation - abs(desired_offset)
        polarity = np.sign(desired_offset)
        correction = -1 * polarity * error * voltage_1MHz  # amount of voltage. Drives in the opposite direction to error. Will require user input for polarity of laser box.
    else:
        error = separation - abs(desired_offset) + correction_array[-1]
        polarity = np.sign(desired_offset)
        correction = -1 * polarity * error * voltage_1MHz  # amount of voltage. Drives in the opposite direction to error. Will require user input for polarity of laser box.
        if np.sign(correction_array[-1]) != np.sign(correction):
            dict_laser_info[4] -= manual_adj_V

    return correction


def get_trace(instr, show_trig_sig):
    """Get current waveform and trigger signal from oscilloscope. Smooth signal data. Returns number of peaks and checks if it is noise/scan amplitude incorrect (over 10 peaks)."""
    # set updated osc settings
    YData = instr.query_str('CHANnel1:DATA? 1')  # Read y data of ch 1
    # print(instr.query_str('CHANnel2:DATA:HEADer?')) when making changes to osc. settings double check that the 4 value is 1 (number of samples per interval)
    TraceData = np.array(YData.split(","), float)
    if show_trig_sig:
        trigger_data = instr.query_str('CHANnel2:DATA? 1')  # Read y data of ch 2
        trigger_data = np.array(trigger_data.split(","), float)

    else:
        trigger_data = []
    peaks, _ = signal.find_peaks(-TraceData,
                                 prominence=0.05)  # size of peaks must be large enough to identify from noise/ramp return peaks
    num_peaks = len(peaks)
    if num_peaks > 10:  # check if noise/scan amplitude incorrect - prevents slow program from extremely long array of peaks.
        num_peaks = 0
    if len(peaks) >= 2:
        separation = peaks[1] - peaks[0]
    else:
        separation = 0
    peaks_loc = peaks[0:2]
    TraceData = TraceData * 0.05*1000  # Osc vertical scale *1000 (milli-volts)
    return TraceData, peaks_loc, num_peaks, separation, peaks, trigger_data


def osc_update(instr, scale, pos):
    """Checks actual horizontal acquisition time. Moves slider value to corresponding value"""
    status_osc = True
    try:
        instr.write('TIMebase:POSition ' + str(pos))  # set position of waveform along horizontal
        instr.write('TIMebase:SCAle ' + str(scale))  # set scale for osc
        read_scale = float((instr.query("TIMebase:RATime?"))) / 12
        scale = read_scale
    except:
        status_osc = False
    return status_osc, scale, pos
