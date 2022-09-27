import PySimpleGUI as sg
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from controls import Signal, status_indicator, osc_update
import csv
from collections import OrderedDict
from flipper_raspi import FlipperControl, PeakIdentification
from base64 import b64encode
import numpy as np
from matplotlib.ticker import FormatStrFormatter
from DAQ_control import DAQ


# from time import sleep


##########################################
# GUI MAIN

def gui_main(instr):
    manual_adj_V = None
    """Main function. Does everything other than DAQ/OSC start up and shut down."""
    fname = "laser_data.csv"  # File containing laser data. (Laser Name, Desired Offset, Default Position, Default Scale, Voltage Corresponding to 1 MHz Change, Voltage Response Rate (sec))
    dict_laser_info = laser_settings(
        fname)  # Laser settings converts the CSV information into a dictionary, with the laser names as keys
    fig_agg, ax, window, canvas, fig_agg_error, ax_error = GUIStartUP(
        dict_laser_info).gui_open_window()  # Opens the GUI window
    laser_name, pos, scale, default_pos, default_scale, dict_laser_info, locking, change_pos, continue_lock, peaks_identified, stage, prev_peaks, mirror_up, loc_mirror, show_trig_sig, laser_lock_status, one_HeNe_FSR, stage, peaks_identified, hene_peak, ident_peaks, mirror_error, in_MHz, status_osc = GUIStartUP(
        dict_laser_info,
        window).initial_set_up()  # Set initial conditions for GUI and variables. Will open last used laser.
    cal_scale = None  # Should be moved into initial conditions
    osc_update(instr, scale, pos)  # Updates the oscilloscope pos/scale with the defaults from the last used laser
    rapid_data = False  # Should be moved into initial conditions
    while 1:
        # get data from osc
        waveform, peaks_loc, separation, pos, num_peaks, scale, laser_lock_status, lost_peaks, trigger_data, correction, voltage_out, uncal_sep, len_waveform \
            = Signal(pos, default_pos, change_pos, locking, in_MHz, continue_lock, scale, laser_lock_status,
                     peaks_identified, ident_peaks, default_scale, dict_laser_info,
                     laser_name, show_trig_sig, manual_adj_V).final_data(instr,
                                                           rapid_data,
                                                           correction_array)  # Retrieves the data from the oscilloscope and returns peak information and locking information. Sends information to the DAQ. This is the main function working behind the scenes of the GUI
        if not locking or change_pos or num_peaks != 2 or not status_osc:  # laser_lock_status controls whether locking occurs and a status LED. Only True when there are only two peaks, user has chosen to lock the laser, the oscilloscope is working fine and the user has disabled change pos
            laser_lock_status = False
        # scaling set up initial
        in_MHz, in_nm = OSCCalibration.calibrate(scale, one_HeNe_FSR, cal_scale,
                                                 len_waveform)  # Returns calibration factor depending on user indicated FSR of the HeNe laser, as well as the current scale. Code could be made faster by calculating the new calibration only when the osc scale or HeNe FSR is reselected, however this is very minor
        # check lock peaks
        no_peaks_check(lost_peaks, window)  # lost peaks is False when there are no peaks
        # read any inputted data from window
        event, values = window.read(timeout=15)
        # react to events
        pos, default_pos, default_scale, scale, status_osc, locking, change_pos, laser_name, dict_laser_info, loc_mirror, one_HeNe_FSR, show_trig_sig, ident_peaks, status_osc, cal_scale, rapid_data, manual_adj_V \
            = GUIEvents(window, default_pos, default_scale, dict_laser_info, laser_name, change_pos, instr,
                        fname="laser_data.csv"). \
            check_events(event, values, pos, window, scale, status_osc, locking, loc_mirror,
                         uncal_sep, one_HeNe_FSR, show_trig_sig, ident_peaks, peaks_identified, cal_scale,
                         rapid_data)  # Checks for any events in the GUI and reacts according to those events
        if hene_peak is not None:
            ident_peaks, peaks_identified = PeakIdentification(ident_peaks, peaks_loc,
                                                               peaks_identified).check_peaks_in_range(hene_peak,
                                                                                                      change_pos,
                                                                                                      waveform)  # Checks that there is a peak within an appropriate range of the previous peak. If it drifted/moved too much within one cycle, will attempt to identify peaks again by returning ident_peaks = True
            hene_peak = peaks_loc[PeakIdentification.find_closest(hene_peak,
                                                                  peaks_loc)]  # Keeps track of the HeNe peak by finding the peak closest to the previous HeNe peak index.
        # update gui
        update_gui(window, fig_agg, separation, num_peaks, status_osc, ax, laser_lock_status,
                   waveform, peaks_loc, loc_mirror, in_nm, in_MHz, trigger_data,
                   hene_peak, peaks_identified, stage, ax_error, correction, fig_agg_error, voltage_out, len_waveform,
                   rapid_data, res_rate=dict_laser_info[laser_name][4])  # Updates GUI - graphs, text values, etc.
        # peak identity
        if ident_peaks and len(peaks_loc) >= 1:
            peaks_identified, stage, prev_peaks, hene_peak, mirror_up, ident_peaks, loc_mirror, mirror_error = PeakIdentification(
                ident_peaks, peaks_loc, peaks_identified).peak_identity(stage, prev_peaks, mirror_up,
                                                                        mirror_error)  # Identifies the peaks by flipping the mirror, blocking the non-hene laser, and matches the index of the remaining peak to the closest of the two peaks after the mirror is lowered again.
            window["-PROG-BAR-"].update(
                current_count=stage * 18)  # Progress bar for peak identification. Stage is dependent on the portion of the peak identification process complete. 18 was chosen as it looked nice and didn't appear to be complete before it actually was (as with 20)
        if mirror_error:  # Mirror error - True when error occurs during peak identification, e.g. more than one peak when the mirror is flipped up (possible that more than one FSR or raspberry pi not connected)
            mirror_error_popup()
            mirror_error = False
        window.refresh()


##########################################
# GUI DESIGN LAYOUT

# variables to use for consistent layout
length_graph = 50
width_graph = 50
radius = 10  # LED radius


class GUILayout:
    def __init__(self, dict_laser_info):
        self.dict_laser_info = dict_laser_info
        self.laser_name, self.desired_offset, self.default_pos, self.default_scale = get_laser_info(
            self.dict_laser_info)

    def define_layout(self):
        """sets entire GUI layout for main window """
        # sets theme
        sg.theme("SystemDefaultForReal")
        icon_fringe_b64 = b64encode(open(r'Fringelockicon.png', 'rb').read())  # opens the application icon
        sg.set_options(font=("Helvetica", 10), button_color=("grey14", "LightCyan3"))  # default font and button colours
        sg.set_options(icon=icon_fringe_b64)  # sets the application icon
        # column (column 1 contains column 2)
        column = self.column_1()
        progress_row = [sg.ProgressBar(max_value=100, orientation="h", key="-PROG-BAR-", visible=False,
                                       bar_color=("grey90", "LightCyan3",), style="clam", border_width=2, size=(10, 2))]
        exit_row = [sg.Push(), sg.Button('Exit', key='-EXIT-', size=(5, 1))]
        layout = [[column], [sg.VPush()], exit_row, progress_row]
        return layout

    def column_1(self):
        """gui layout for RHS, display, oscilloscope controls, status LEDs"""
        title_row = [sg.Text('Frequency Offset Lock', size=(40, 1),
                             justification='center', font='Helvetica 14')]
        # change laser button, opens a new window
        button_change_laser = sg.Button("Change Laser", key="-CHANGE-LASER-", enable_events=True,
                                        tooltip="Change Selected Laser, Add/Remove Lasers")
        # change scaling set up button
        button_change_scale = sg.Button("Reset Scale Set Up", key="-CHANGE-SCALE-SETUP-",
                                        enable_events=True)
        # show trigger signal button
        button_show_trigger = sg.Button("Hide Trigger Signal", key="-SHOW-TRIG-", enable_events=True,
                                        auto_size_button=True)
        # identify peaks button
        identify_peaks_button = sg.Button("Identify Peaks", key="-IDEN-PEAKS-", enable_events=True,
                                          auto_size_button=True)
        # display frame, contains graph and info text
        display_frame = sg.Frame("Display",
                                 [[sg.Canvas(size=(380, 260), key='-CANVAS-WAVEFORM-', pad=(65, 10), expand_x=True,
                                             expand_y=True)],
                                  [sg.Canvas(size=(380, 60), key='-CANVAS-ERROR-', pad=(65, 10), expand_x=True,
                                             expand_y=False)],
                                  [sg.Text(f'Peak Separation: ', key='-SEP-TEXT-')],
                                  [sg.Text(f'', key='-SEL-LASER-'),
                                   sg.Text(f'Desired Offset: ', key='-OFF-TEXT-'), button_change_laser,
                                   button_change_scale], [button_show_trigger, identify_peaks_button],
                                  [sg.Text('Manual Voltage Output')], [sg.Slider(range=(-5, 5), size=(60, 15),
                                                                                 orientation='h',
                                                                                 key='-SLIDER-MANUAL-V-',
                                                                                 enable_events=True, resolution=0.001,
                                                                                 default_value=0,
                                                                                 disable_number_display=False,
                                                                                 disabled=False,
                                                                                 tooltip="Manual Change in Output Voltage.",
                                                                                 pad=((0, 0), (0, 17)),
                                                                                 trough_color='grey90')],
                                  [sg.Button('Return to 0', key='-RETURN0-MANUALV-', size=(8, 2))],
                                  [sg.Text('Change in voltage calibration amount')], [sg.Input(expand_x=True, expand_y=True, do_not_clear=True,
                                                                                               key='-V-CAL-MANUAL-ADJ-',
                                                                                               size=(6, 1))]])
        # controls
        pos_controls_row = [sg.Button('Change Default', key='-CHANGE-DEFAULT-POS-', size=(8, 2)),
                            sg.Button('Default', key='-DEFAULT-POS-', size=(8, 1)),
                            sg.Slider(range=(0.01, 0.5), size=(60, 15),
                                      orientation='h', key='-SLIDER-POS-', enable_events=True, resolution=0.01,
                                      default_value=self.default_pos, disable_number_display=False, disabled=True,
                                      tooltip="Enable 'Change Position' for manual changes in trigger reference position.",
                                      pad=((0, 0), (0, 17)), trough_color='grey90'),
                            sg.Button('Change', key='-CHANGE-POS-', auto_size_button=True)]
        scale_controls_row = [sg.Button('Change Default', key='-CHANGE-DS-', size=(8, 2)),
                              sg.Button('Default', key='-DEFAULT-SCALE-', size=(8, 1)),
                              sg.Combo(values=[0.001, 0.0025, 0.006, 0.0075, 0.01], default_value=self.default_scale, size=(8, 1),
                                       enable_events=True, key='-SCALE-VALUE-', background_color='grey90',
                                       text_color='grey14', readonly=True)]
        # scale is not a slider as limited slider values give the correct number of data points
        # make sure that all values in scale range returns the same number of data points.
        # can add more values, check that actual scale from osc (read_scale in osc_update()) matches closely to value
        controls_row = [[sg.Text('Manually Adjust Position')], pos_controls_row,
                        [sg.Text('Manually Adjust Scale')], scale_controls_row,
                        [sg.Text(f'Default Pos: ', key='-POS-TEXT-')],
                        [sg.Text(f'Default Scale: ', key='-SCALE-TEXT-')]]
        osc_control_frame = [sg.Frame("Oscilloscope Controls", controls_row)]
        # LED status row layout
        led_status_row = [sg.Text('Lock Status:'), GUILED.LEDIndicator(key='-LED-LOCK-'), sg.Text('Peak Status:'),
                          GUILED.LEDIndicator(key='-LED-PEAK-'),
                          sg.Text('Osc Status:'), GUILED.LEDIndicator(key='-LED-OSC-')]
        # button for laser locking. Red if off, green if on
        lock_row = [sg.Button(button_text='Lock', key='-LASER-LOCKING-', size=(6, 1),
                              button_color='tomato')]
        # column layout
        column1 = sg.Column([title_row, [display_frame, self.column_2()], osc_control_frame, led_status_row, lock_row],
                            element_justification='center', expand_x=True)
        return column1

    def column_2(self):
        """column 2 of main layout, defines mirror buttons, trigger slider, voltage response rate, averaging selection"""
        # gui layout for manual controls for flipper mirror, up sends HeNe light into beam dump (not in FPI, no peak)
        mirror_switch = sg.Graph(canvas_size=(width_graph, length_graph), graph_bottom_left=(0, 0),
                                 graph_top_right=(width_graph, 2),
                                 drag_submits=True,
                                 key="-MIRROR-CONTROL-", enable_events=True)
        mirror_switch_bottom_text = sg.T('Down', size=(6, 1), font=("Helvetica", 8), justification='center')
        mirror_switch_top_text = sg.T('Up', size=(6, 1), font=("Helvetica", 8), justification='center')

        mirror_frame = sg.Frame(title="Mirror Control",
                                layout=[[mirror_switch_top_text], [mirror_switch], [mirror_switch_bottom_text]],
                                element_justification='center')
        # Slider for trigger level
        trigger_slider = sg.Slider(range=(-1, -3), size=(8, 10),
                                   orientation='v', key='-SLIDER-TRIG-', enable_events=True, resolution=0.1,
                                   default_value=-2, disable_number_display=False,
                                   tooltip="Change Trigger Level", trough_color='grey90')
        trigger_frame = sg.Frame(title="Trigger Level", layout=[[trigger_slider]], element_justification='left')
        # input for voltage response rate. can go up/down by 0.01 using arrow keys on keyboard
        speed_input = sg.Input(f'{self.dict_laser_info[self.laser_name][4]}', do_not_clear=True,
                               key="-V-RATE-", size=(6, 1))
        speed_input_text = sg.Text("Voltage Rate")
        speed_input_text_sec = sg.Text("(sec)")
        response_speed_frame = sg.Frame(title="Voltage Response",
                                        layout=[[speed_input_text], [speed_input, speed_input_text_sec]],
                                        element_justification='left')
        # controls for oscilloscope acquisition mode (waveform priority (rapid) or AUTO)
        rapid_data_button = sg.Button("Rapid Data Collection", key="-RAPID-DATA-",
                                      tooltip="Collects data at a much faster rate, but reduces resolution significantly.")
        averaging_frame = sg.Frame("Average Count", [[sg.Combo([2, 4, 8, 16, 32, 64, 128], default_value=2,
                                                               key="-AVG-COUNT-", readonly=True, enable_events=True,
                                                               text_color='grey14', background_color='grey90')]])
        column = sg.Column(
            [[mirror_frame], [trigger_frame], [response_speed_frame], [averaging_frame], [rapid_data_button]],
            element_justification='center')
        return column

    @staticmethod
    def change_laser_layout():
        """Defines layout for laser settings window"""
        # opens empty list box. values are added from laser information dictionary when window is opened
        laser_selection = sg.Listbox([""], key="-SELECT-LASER-", size=(10, 10), enable_events=True,
                                     highlight_background_color="LightCyan3")
        laser_selection_frame = sg.Frame("Laser Selection",
                                         [[laser_selection, sg.Button("Done", key="-DONE-CHANGE-LASER-")],
                                          [sg.Button(button_text="Delete", key='-DELETE-LASER-')]])
        laser_entry = ["Laser Name: ", "Desired Offset (MHz): ", "Voltage for 1 MHz Change: "]
        # user input boxes. Only submits input once button is pressed
        new_laser_elements = [[sg.Push(), sg.Text(label), sg.Input(key=label.split()[0], enable_events=False)] for label
                              in laser_entry] + [
                                 [sg.Push(), sg.Button('Ok', key='-NEW-LASER-OK-', bind_return_key=True)]]
        new_laser_info = sg.Frame("Enter New Laser", new_laser_elements)
        selected_laser_values = [sg.Text(
            "Laser Name: \n Desired Offset: \n Default Position: \n Default Scale: \n Voltage for 1 MHz Change: ",
            key="-SEL-LASER-VALUES-")]
        laser_value_frame = sg.Frame("Selected Laser", [selected_laser_values])
        close_button = [sg.Push(), sg.Button("Close", key="-CLOSED-")]
        layout = [[laser_selection_frame, laser_value_frame], [new_laser_info], [close_button]]
        return layout


##########################################
# GUI DISPLAY AND CHANGES

class GUILED:
    def __init__(self, window):
        self.window = window

    def setLED(self, key, color):
        """changes the color of the LED circle"""
        graph = self.window[key]
        graph.erase()
        graph.draw_circle((0, 0), 14, fill_color=color, line_color="grey14")

    @staticmethod
    def LEDIndicator(key=None, radiusLED=30):
        """create LED object for status indication"""
        return sg.Graph(canvas_size=(radiusLED, radiusLED),
                        graph_bottom_left=(-radiusLED, -radiusLED),
                        graph_top_right=(radiusLED, radiusLED),
                        pad=((0, 0), (5, 0)), key=key)


# Tkinter functions for graph animation
def draw_figure(canvas, figure):
    """Tkinter controls for drawing a figure, for animation"""
    figure_canvas_agg = FigureCanvasTkAgg(figure, canvas)
    figure_canvas_agg.draw()
    figure_canvas_agg.get_tk_widget().pack(side='top', fill='both', expand=True)
    return figure_canvas_agg


# Start up commands for GUI
class GUIStartUP:
    # initial conditions for variables
    def __init__(self, dict_laser_info, window=None):
        self.dict_laser_info = dict_laser_info
        self.window = window
        self.locking = False
        self.change_pos = False
        self.continue_lock = False
        self.peaks_identified = False
        self.stage = 0
        self.prev_peaks = None
        self.mirror_up = True
        self.loc_mirror = 1
        self.show_trig_sig = True
        self.laser_lock_status = False
        self.one_HeNe_FSR = None
        self.stage = 0
        self.peaks_identified = False
        self.hene_peak = None
        self.ident_peaks = False  # identify the peaks

    def gui_open_window(self):
        """"Opens the GUI window"""
        layout = GUILayout(self.dict_laser_info).define_layout()
        # create the window
        window = sg.Window('Fringe Offset Lock - Main Page',
                           layout, finalize=True, resizable=True)
        # restricts minimum size for window
        window.TKroot.minsize(700, 1020)
        # binds the enter key and arrow keys to the voltage response rate input box
        window["-V-RATE-"].bind("<Return>", "_Enter")
        window["-V-RATE-"].bind("<Up>", "_UpArrowKey")
        window["-V-RATE-"].bind("<Down>", "_DownArrowKey")
        # defines the canvas element for plotting the waveform graph
        canvas_elem = window["-CANVAS-WAVEFORM-"]
        # create figure for display
        fig = Figure(edgecolor="#242424", linewidth=2)
        ax = fig.add_subplot(111)
        canvas = canvas_elem.TKCanvas
        fig_agg = draw_figure(canvas, fig)
        # defines the canvas element for plotting the error graph
        canvas_elem_error = window["-CANVAS-ERROR-"]
        # create figure for display
        fig_error = Figure(edgecolor="#242424", linewidth=2, figsize=(5, 2))
        ax_error = fig_error.add_subplot(111)
        canvas_error = canvas_elem_error.TKCanvas
        fig_agg_error = draw_figure(canvas_error, fig_error)
        # cursors
        window['-SCALE-VALUE-'].set_cursor("hand2")
        window['-SLIDER-TRIG-'].set_cursor("sb_v_double_arrow")
        return fig_agg, ax, window, canvas, fig_agg_error, ax_error

    def initial_set_up(self):
        """Initial set up for gui and settings"""
        laser_name, desired_offset, default_pos, default_scale = get_laser_info(
            self.dict_laser_info)  # gets laser information from dictionary
        pos = default_pos  # sets current pos to default pos
        scale = default_scale  # sets current scale to default scale
        # match gui to settings
        self.gui_initial_settings()
        # flips up the mirror for faster calibration
        FlipperControl.flipper_on()
        status_osc = True
        mirror_error = False
        in_MHz = None
        return laser_name, pos, scale, default_pos, default_scale, self.dict_laser_info, self.locking, self.change_pos, self.continue_lock, self.peaks_identified, self.stage, self.prev_peaks, self.mirror_up, self.loc_mirror, self.show_trig_sig, self.laser_lock_status, self.one_HeNe_FSR, self.stage, self.peaks_identified, self.hene_peak, self.ident_peaks, mirror_error, in_MHz, status_osc

    def gui_initial_settings(self):
        """Initial settings, based on the first row in CSV. Sets proper values from dictionary for variables and GUI"""
        laser_name, desired_offset, default_pos, default_scale = get_laser_info(self.dict_laser_info)
        self.window['-SCALE-TEXT-'].update(value=f'Default Scale: {default_scale:.7}')
        self.window['-POS-TEXT-'].update(value=f'Default Pos: {default_pos:.6}')
        self.window["-OFF-TEXT-"].update(value=f'Desired Offset: {desired_offset} MHz')
        self.window["-SEL-LASER-"].update(value=f'Laser: {laser_name}')
        self.window["-SCALE-VALUE-"].update(value=default_scale)
        self.window["-SLIDER-POS-"].update(value=default_pos)


# Voltage output graph
class ErrorValuesGraph:
    def __init__(self, correction, voltage_out):
        self.correction = correction
        self.voltage_out = voltage_out

    def graph_error_signal(self, ax_error):
        global qy
        correction_array = self.error_array()  # updates correction array
        try:
            ax_error.spines['top'].set_visible(False)
            ax_error.spines['right'].set_visible(False)
            ax_error.spines['bottom'].set_position('zero')
            ax_error.set_ylabel("Volts", labelpad=0.2)
            ax_error.xaxis.set_visible(False)
            max_cor = np.amax(np.abs(correction_array))
            ax_error.set_ylim([-max_cor - 0.05, max_cor + 0.05])
            ax_error.set_xlim([0, 51])
            line_colour = "#ED798D"
            ax_error.plot(correction_array, color=line_colour, linewidth=2)
            ax_error.text(len(correction_array), correction_array[-1],
                          f'{correction_array[-1]:.3f}')  # text displaying most recent voltage output value
        except (TypeError, ValueError):
            pass

    def error_array(self):
        """Updates correction array with new correction value. Only keeps 50 most recent data points"""
        global correction_array
        if self.correction is not None and self.voltage_out:
            correction_array = np.append(correction_array, self.correction)
            if len(correction_array) >= 50:
                correction_array = np.delete(correction_array, 0)
        return correction_array


def draw_mirror_slider(graph, loc):
    """Draws mirror slider graphic"""
    graph.erase()
    mirror_up = False
    # loc is the location on the graph that the user selected, 1 is the midpoint
    if loc < 1:
        mirror_up = False
    elif loc >= 1:
        mirror_up = True

    if not mirror_up:
        graph.draw_rectangle(bottom_right=(width_graph / 2 - 5, 0.2), top_left=(width_graph / 2 + 5, 0.6),
                             fill_color="grey14")
        graph.draw_rectangle(bottom_right=(width_graph / 2 - 5, 1.4), top_left=(width_graph / 2 + 5, 1.8),
                             fill_color="LightCyan3")
        graph.draw_line(point_from=(width_graph / 2 - 5, 0.2), point_to=(width_graph / 2 + 5, 0.6), color="LightCyan3")
        graph.draw_line(point_from=(width_graph / 2 + 5, 0.2), point_to=(width_graph / 2 - 5, 0.6), color="LightCyan3")

    elif mirror_up:
        graph.draw_rectangle(bottom_right=(width_graph / 2 - 5, 1.4), top_left=(width_graph / 2 + 5, 1.8),
                             fill_color="grey14")
        graph.draw_rectangle(bottom_right=(width_graph / 2 - 5, 0.2), top_left=(width_graph / 2 + 5, 0.6),
                             fill_color="LightCyan3")
        graph.draw_line(point_from=(width_graph / 2 - 5, 1.4), point_to=(width_graph / 2 + 5, 1.8), color="LightCyan3")
        graph.draw_line(point_from=(width_graph / 2 + 5, 1.4), point_to=(width_graph / 2 - 5, 1.8), color="LightCyan3")
    graph.set_cursor("hand2")


def update_gui(window, fig_agg, separation, num_peaks, status_osc, ax, laser_lock_status, waveform,
               peaks_loc, loc_mirror, in_nm, in_MHz, trigger_data, loc_closest,
               peaks_identified, stage, ax_error, correction, fig_agg_error, voltage_out, len_waveform, rapid_data,
               res_rate):
    """Updates all GUI values and graphics"""
    # only show peak separation if has been converted to MHz. Small bug where it shows the non MHz version for one loop but shouldn't affect functionality
    try:
        if in_MHz is not None:
            window['-SEP-TEXT-'].update(value=f'Peak Separation: {separation:.2f}  MHz')
    except ValueError:
        window['-SEP-TEXT-'].update(value=f'Peak Separation: N/A')
    status_peak = status_indicator(num_peaks, separation,
                                   in_MHz)  # True if there are two peaks and peaks are not 3000 MHz apart (indicating that they are from the same laser)
    # update peaks status + LED. If value is True, LED is green, else the LED is red. Could be made into a separate function
    GUILED(window).setLED('-LED-PEAK-', 'forest green' if status_peak else 'tomato')
    GUILED(window).setLED('-LED-OSC-', 'forest green' if status_osc else 'tomato')
    GUILED(window).setLED('-LED-LOCK-', 'forest green' if laser_lock_status else 'tomato')
    # progress bar for peak identity
    if stage != 0:
        window["-PROG-BAR-"].update(visible=True)
    else:
        window["-PROG-BAR-"].update(visible=False)
    # makes response rate 1.5 if in slow data collection and chosen response rate <1.5. Doesn't change value in CSV until user changes value
    if not rapid_data and res_rate < 1.5:
        window['-V-RATE-'].update(value=1.5)
    # mirror slider
    draw_mirror_slider(window["-MIRROR-CONTROL-"], loc_mirror)
    # clear plots and draw new graph. would be faster not to redraw axis but cannot figure out how to do it without clearing the entire plot (and still have the tick marks move according to data values)
    ax.clear()
    ax.grid()
    ax.minorticks_on()
    animate(ax, waveform, peaks_loc, in_MHz, trigger_data, loc_closest, peaks_identified, len_waveform)
    fig_agg.draw()
    ErrorValuesGraph(correction, voltage_out).graph_error_signal(ax_error)
    fig_agg_error.draw()
    ax_error.clear()
    ax_error.grid()
    ax_error.minorticks_on()


def animate(ax, waveform, peaks_loc, in_MHz, trigger_data, hene_peak, peaks_identified, len_waveform):
    line_colour = "#5F9EA0"
    x_axis_points, peaks_loc_cal, x_axis_points_trig, hene_peak_cal = OSCCalibration.cal_hene(in_MHz, ax, peaks_loc,
                                                                                              trigger_data, hene_peak,
                                                                                              len_waveform)
    # plot the signal, and the first 2 detected peaks by scipy

    if len(trigger_data) != 0:
        ax.plot(x_axis_points_trig, -trigger_data)
    # plot waveform
    ax.plot(x_axis_points, waveform, color=line_colour, linewidth=2)
    ax.plot(peaks_loc_cal, waveform[peaks_loc], 'x', color="#7223B4", linewidth=2)
    # plot hene peak identifiers
    if peaks_identified and hene_peak is not None:  # plots red x and "HeNe" text on HeNe peak
        ax.plot(hene_peak_cal, waveform[hene_peak], 'x', color="r", linewidth=10)
        ax.text(hene_peak_cal, (waveform[hene_peak] - 2), "HeNe")
    # set axis limits to reduce movement of axis
    if -15 <= min(waveform) <= 1:
        ax.set_ylim([-15, 1])
    # turn off top and right axis for aesthetics
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    # label x-axis in MHz only when calibrated and HeNe peak identified
    if in_MHz is not None and hene_peak is not None:
        ax.set_xlabel("MHz", labelpad=0.2)
    # label y-axis
    ax.set_ylabel("Millivolts", labelpad=0.2)
    ax.yaxis.set_major_formatter(FormatStrFormatter('%.00f'))


##########################################
# GUI EVENTS

class GUIEvents:
    def __init__(self, window=None, default_pos=None, default_scale=None, dict_laser_info=None, laser_name=None,
                 change_pos=None, instr=None,
                 fname=None):
        self.change_pos = change_pos
        self.default_pos = default_pos
        self.default_scale = default_scale
        self.dict_laser_info = dict_laser_info
        self.laser_name = laser_name
        self.fname = fname
        self.window = window
        self.desired_offset = None
        self.res_rate = self.dict_laser_info[self.laser_name][4]
        self.instr = instr

    def check_events(self, event, values, pos, window, scale, status_osc, locking, loc_mirror,
                     uncal_sep, one_HeNe_FSR, show_trig_sig,
                     ident_peaks, peaks_identified, cal_scale, rapid_data):
        """Check all events in the GUI and react accordingly"""
        manual_adj_V = 0
        if event in '-SLIDER-MANUAL-V-':
            manual_voltage = float(values['-SLIDER-MANUAL-V-'])
            ErrorValuesGraph(manual_voltage, True).error_array()
            DAQ.daq_output(manual_voltage)
        if event in '-RETURN0-MANUALV-':
            manual_voltage = 0
            ErrorValuesGraph(manual_voltage, True).error_array()
            DAQ.daq_output(manual_voltage)
            window['-SLIDER-MANUAL-V-'].update(value=0)
        if event in '-V-CAL-MANUAL-ADJ-':
          manual_adj_V = float(values['-V - CAL - MANUAL - ADJ -'])

        if event == '-EXIT-' or event == sg.WIN_CLOSED:
            self.close_window()
        if event in "-CHANGE-LASER-":
            # change selected laser. Opens new window. Blocks events in main window until change laser window is closed
            window.DisableClose = True
            scale, pos = self.change_laser()
            window.DisableClose = False
        if event in "-SLIDER-MANUAL-V-":
            correction = float(values['-SLIDER-MANUAL-V-'])
            # DAQ_control.DAQ().daq_output(correction)
        if event == "-V-RATE-" + "_Enter":
            # input voltage output rate
            self.user_enter_vrate(values, rapid_data)
        if event == "-V-RATE-" + "_UpArrowKey":
            # increase voltage output rate using up arrow key
            self.uarrow_vrate(values)
        if event == "-V-RATE-" + "_DownArrowKey":
            # decrease voltage output rate using down arrow key
            self.darrow_vrate(values, rapid_data)
        if event in '-CHANGE-POS-':
            # change oscilloscope horizontal position
            self.enable_change_pos()
        if event in '-SLIDER-POS-' and self.change_pos:
            pos = float(values['-SLIDER-POS-'])
            # if manual pos adjust on, then slider value is pos
            status_osc, scale, pos = osc_update(self.instr, scale, pos)
        if event in '-DEFAULT-POS-':
            # return to default pos
            pos = self.default_pos
        if event in '-CHANGE-DEFAULT-POS-':
            # set current pos as the new default
            self.change_default_pos(values)
        if event in '-DEFAULT-SCALE-':
            # return to default scale
            scale = self.default_scale
        if event in '-SCALE-VALUE-':
            # changes the oscilloscope scale
            scale = float(values['-SCALE-VALUE-'])
            status_osc, scale, pos = osc_update(self.instr, scale, pos)
        if event in '-CHANGE-DS-':
            # set the current scale as the new default - save to CSV file
            self.default_scale = scale
            self.change_default_scale()
        if event in '-LASER-LOCKING-':
            # enables/disables laser locking
            locking = self.enable_laser_lock(locking, peaks_identified, one_HeNe_FSR)
        if event in "-MIRROR-CONTROL-":
            # changes mirror position
            loc_mirror = self.manual_mirror_control(values)
        if event in "-SLIDER-TRIG-":
            # changes trigger level
            self.change_trig_level(self.instr, values)
        if event in "-SHOW-TRIG-":
            # shows/hides trigger signal
            show_trig_sig = self.hide_trigger(show_trig_sig)
        if event in "-CHANGE-SCALE-SETUP-":
            # changes scaling factor
            one_HeNe_FSR, cal_scale = check_FSR(one_HeNe_FSR, uncal_sep, scale, rapid_data)
        if event in "-IDEN-PEAKS-":
            # initiates peak identification process
            ident_peaks = True
        if event in "-RAPID-DATA-":
            # enables 'rapid data collection' on oscilloscope - prioritises number of waveforms, fewer data points, faster data transfer
            rapid_data = self.enable_rapid_data(rapid_data)
            if rapid_data:
                window['-V-RATE-'].update(value=self.res_rate)
        if event in "-AVG-COUNT-":
            # changes number of waveforms used by oscilloscope for averaging
            avg = str(values["-AVG-COUNT-"])
            self.instr.write('ACQuire:AVERage:COUNt ' + avg)
        return pos, self.default_pos, self.default_scale, scale, status_osc, locking, self.change_pos, self.laser_name, self.dict_laser_info, loc_mirror, one_HeNe_FSR, show_trig_sig, ident_peaks, status_osc, cal_scale, rapid_data, manual_adj_V

    # CLOSE WINDOW
    def close_window(self):
        """Closes main window. First rewrites CSV file in order to have last selected laser to open first upon the next start-up"""
        with open(self.fname, 'r+') as dF:  # wipes CSV file
            dF.truncate()
        with open(self.fname, 'a') as f:  # rewrites CSV file
            self.dict_laser_info.move_to_end(self.laser_name,
                                             last=False)  # moves selected laser to the first position in dict
            writer = csv.writer(f)
            for key, value in self.dict_laser_info.items():
                value.insert(0, key)
                writer.writerow(value)
        self.window.close()  # closes main window
        raise SystemExit("Main Window Closed")  # for confirmation that program didn't crash

    # CHANGE LASER FUNCTIONS
    def change_laser(self):
        """Changes variables to correspond with new selected laser. Updates text in window with correct values"""
        self.laser_name, self.default_pos, self.default_scale, self.dict_laser_info = self.open_change_laser_window()
        self.desired_offset = self.dict_laser_info[self.laser_name][0]
        # updates GUI texts to match changed variable values
        self.window["-OFF-TEXT-"].update(value=f'Desired Offset: {self.desired_offset} MHz')
        self.window["-SEL-LASER-"].update(value=f'Laser: {self.laser_name}')
        scale = self.default_scale
        pos = self.default_pos
        return scale, pos

    def open_change_laser_window(self):
        """Opens change laser window, and reacts to events"""
        # layout for change laser window
        layout = GUILayout.change_laser_layout()
        # opens window
        change_laser_window = sg.Window("Change Laser", layout, finalize=True, modal=False)
        self.change_laser_window_start_up(change_laser_window)  # Start up settings
        while 1:
            event, values = change_laser_window.read(timeout=10)
            try:
                if event in '-SELECT-LASER-':
                    # Updates variables depending on new selected laser
                    self.laser_name = values["-SELECT-LASER-"][0]
                    self.get_selected_laser_info(change_laser_window)
                if event in "-DELETE-LASER-":
                    # Deletes laser option from listbox + CSV file
                    self.delete_laser(change_laser_window)
                if event in "-NEW-LASER-OK-":
                    # Adds new laser to CSV and updates the dictionary. Clears input boxes.
                    self.add_laser(values, change_laser_window)
                    change_laser_window["Laser"]('')
                    change_laser_window["Desired"]('')
                    change_laser_window["Voltage"]('')
            except (TypeError, IndexError):  # If issue with entries that wasn't caught by check entries function
                pass
            if event == sg.WIN_CLOSED or event in "-CLOSED-" or event in "-DONE-CHANGE-LASER-":
                # sets pos and slider GUI elements to match new values
                self.window["-SCALE-VALUE-"].update(value=self.default_scale)
                self.window["-SLIDER-POS-"].update(value=self.default_pos)
                change_laser_window.close()
                break
        if not self.dict_laser_info:
            # If dict_laser_info is empty (False) reopens laser change window to force user to add a laser to select
            self.open_change_laser_window()
        return self.laser_name, self.default_pos, self.default_scale, self.dict_laser_info

    def change_laser_window_start_up(self, change_laser_window):
        """Start up settings for change laser window"""
        try:
            # Updates listbox options, and highlights the selected laser
            change_laser_window["-SELECT-LASER-"].update(values=self.dict_laser_info.keys())
            change_laser_window["-SELECT-LASER-"].update(
                set_to_index=list(self.dict_laser_info.keys()).index(self.laser_name))
            # Get selected laser info
            self.get_selected_laser_info(change_laser_window)
        except (ValueError, IndexError):
            # If issue with selected laser (e.g. none selected due to all options being deleted) shows blank listbox and info box
            change_laser_window["-SEL-LASER-VALUES-"].update(
                f'Laser Name:  \n Desired Offset: \n Default Position: \n Default Scale:\n Voltage for 1 MHz Change: ')
            change_laser_window["-SELECT-LASER-"].update(
                set_to_index=None)

    def get_selected_laser_info(self, change_laser_window):
        """Returns variables corresponding to selected laser and updates values in info box"""
        # Defines laser info dictionary values from CSV file
        self.dict_laser_info = laser_settings(self.fname)
        self.default_pos = self.dict_laser_info[self.laser_name][1]  # retrieve default pos for that laser
        self.default_scale = self.dict_laser_info[self.laser_name][2]  # retrieve default scale for that laser
        # updates change laser info text box with values
        change_laser_window["-SEL-LASER-VALUES-"].update(
            f'Laser Name: {self.laser_name} \n Desired Offset: {self.dict_laser_info[self.laser_name][0]} \n Default Position: {self.default_pos}\n Default Scale: {self.default_scale} \n Voltage for 1 MHz Change: {self.dict_laser_info[self.laser_name][3]}')
        # updates main window text values - not sure if this works since window is disabled??
        self.window['-SCALE-TEXT-'].update(value=f'Default Scale: {self.default_scale:.7}')
        self.window['-POS-TEXT-'].update(value=f'Default Pos: {self.default_pos:.7}')

    def delete_laser(self, change_laser_window):
        """Deletes laser from CSV using del_laser then updates listbox. Automatically selects the first value in listbox"""
        # deletes laser from CSV
        CSVControls(self.fname, self.laser_name).del_laser()
        # remakes laser information dictionary
        self.dict_laser_info = laser_settings(self.fname)
        # updates listbox options with new dictionary keys
        change_laser_window["-SELECT-LASER-"].update(values=self.dict_laser_info.keys())
        # highlights first option in listbox
        change_laser_window["-SELECT-LASER-"].update(set_to_index=0)
        # first laser in list now selected
        self.laser_name = list(self.dict_laser_info.keys())[0]
        # change selected laser to lock
        self.get_selected_laser_info(change_laser_window)

    def add_laser(self, values, change_laser_window):
        """Adds inputted values into CSV and updates dictionary. Automatically selects newly added laser."""
        # enter inputted value as a new laser
        laser_name = str.strip(values["Laser"])
        laser_frequency = str.strip(values["Desired"])
        laser_volt_frequency = str.strip(values["Voltage"])
        # ensures that entry is valid
        if check_entry(self.laser_name, laser_frequency):
            # ensure all entries are filled
            new_laser_info = f"{laser_name}, {laser_frequency}, 0.08, 0.002, {laser_volt_frequency}, 1.0"  # 0.08 = def pos for new laser, 0.002 = def scale for new laser, 2 sec = def voltage output rate
            # adds new laser info to CSV
            CSVControls(self.fname).add_laser_csv(new_laser_info)
            self.laser_name = laser_name
            self.dict_laser_info = laser_settings(self.fname)
            change_laser_window["-SELECT-LASER-"].update(values=self.dict_laser_info.keys())
            change_laser_window["-SELECT-LASER-"].update(set_to_index=len(self.dict_laser_info.keys()) - 1)
            self.get_selected_laser_info(change_laser_window)
        else:
            pass

    # CHANGE VOLTAGE OUTPUT RATE FUNCTIONS
    def change_V_rate(self, res_rate):
        """Updates voltage output rate in CSV and dictionary"""
        self.res_rate = res_rate
        CSVControls(self.fname, self.laser_name).update_defaults(self.default_pos, self.default_scale, self.res_rate)
        self.dict_laser_info = laser_settings(self.fname)

    def user_enter_vrate(self, values, rapid_data):
        """Updates voltage rate depending on user inputted value. Must be a valid entry. Must be larger than 0.4 (limited by speed of code)"""
        try:
            if rapid_data:
                min_rate = 0.4
            else:
                min_rate = 1.2
            res_rate = float(values['-V-RATE-'])
            if res_rate >= min_rate:
                self.change_V_rate(res_rate)
            else:
                raise ValueError
        except ValueError:
            self.window['-V-RATE-'].update(
                value=self.dict_laser_info[self.laser_name][4])  # makes rate previously saved value

    def darrow_vrate(self, values, rapid_data):
        """Decreases voltage output rate by 0.01 using keyboard down arrow. Limited due to speed of code"""
        if rapid_data:
            min_rate = 0.4
        else:
            min_rate = 1.2
        if float(values['-V-RATE-']) >= min_rate:
            res_rate = round(float(values['-V-RATE-']) - 0.01, 2)
            self.window["-V-RATE-"].update(value=res_rate)
            self.change_V_rate(res_rate)

    def uarrow_vrate(self, values):
        """Increases voltage output rate by 0.01 using keyboard down arrow"""
        res_rate = round(float(values['-V-RATE-']) + 0.01, 2)
        self.window["-V-RATE-"].update(value=res_rate)
        self.change_V_rate(res_rate)

    # OSC HORIZONTAL POSITION FUNCTIONS
    def enable_change_pos(self):
        """Button that enables/disables changing oscilloscope x-axis position (Reference to trigger). Will enable/disable slider control."""
        # button for manual pos adjustment
        self.change_pos = not self.change_pos
        self.window['-CHANGE-POS-'].update(button_color='forest green' if self.change_pos else 'LightCyan3')
        # set slider cursor
        self.window['-SLIDER-POS-'].set_cursor("sb_h_double_arrow" if self.change_pos else 'arrow')
        self.window['-SLIDER-POS-'].update(disabled=False if self.change_pos else True)

    def change_default_pos(self, values):
        """Changes default pos to current position. Updates CSV/Dict."""
        self.default_pos = float(values['-SLIDER-POS-'])
        self.window['-POS-TEXT-'].update(value=f'Default Pos: {self.default_pos:.6} ')
        CSVControls(self.fname, self.laser_name).update_defaults(self.default_pos, self.default_scale, self.res_rate)
        self.dict_laser_info = laser_settings(self.fname)

    # OSC TIME SCALE FUNCTIONS

    def change_default_scale(self):
        """Changes default time scale to current scale. Updates CSV/Dict."""
        self.window['-SCALE-TEXT-'].update(value=f'Default Scale: {self.default_scale:.7}')
        CSVControls(self.fname, self.laser_name).update_defaults(self.default_pos, self.default_scale, self.res_rate)
        self.dict_laser_info = laser_settings(self.fname)

    # ENABLE/DISABLE LASER LOCK
    def enable_laser_lock(self, locking, peaks_identified, one_HeNe_FSR):
        """Set laser locking on or off. Locking is enabled if peaks are identified and scaling of x-axis has been complete.
         Popups will appear if those conditions are not met. Turns lock button red (locking off) or green (locking on).
         """
        locking = not locking
        if locking and not peaks_identified:
            lock_error_peaks_iden_popup()
            locking = False
        if locking and not one_HeNe_FSR:
            lock_error_scale_popup()
            locking = False
        self.window['-LASER-LOCKING-'].update(button_color='forest green' if locking else 'red')
        return locking

    # MIRROR CONTROL
    @staticmethod
    def manual_mirror_control(values):
        """Moves flipper mirror up or down. If user selection is >= 1, mirror is moved up (blocking beam), else it is moved down. """
        loc_mirror = values["-MIRROR-CONTROL-"][1]
        if loc_mirror >= 1.:
            FlipperControl.flipper_on()
        elif loc_mirror == 0:
            FlipperControl.flipper_off()
        return loc_mirror

    @staticmethod
    def change_trig_level(instr, values):
        """Changes trigger level on oscilloscope"""
        instr.write('TRIGger:A:LEVel2 ' + f'{-1 * values["-SLIDER-TRIG-"]}')

    def hide_trigger(self, show_trig_sig):
        """Hides trigger signal on display. If trigger signal is hidden, no trigger data received from oscilloscope"""
        show_trig_sig = not show_trig_sig
        self.window["-SHOW-TRIG-"].Update('Hide Trigger Signal' if show_trig_sig else 'Show Trigger Signal')
        return show_trig_sig

    def enable_rapid_data(self, rapid_data):
        rapid_data = not rapid_data
        self.window['-RAPID-DATA-'].update(button_color='forest green' if rapid_data else 'LightCyan3')
        if rapid_data:
            self.instr.write('ACQuire:WRATe MWAVeform')  # only 600 data points but very fast.
        else:
            self.instr.write('ACQuire:WRATe AUTO')
        return rapid_data


##########################################
# LASER SETTINGS

class OSCCalibration:
    @staticmethod
    def calibrate(scale, one_HeNe_FSR, cal_scale, len_waveform):
        """Calibrates the x-axis/peak separation assuming a 300 MHz FSR using two HeNe peaks.
        Use scan generator offset only to change number of HeNe peaks.
        Changing frequency or amplitude will change calibration and cause improper locking.
        Assumes waveform from oscilloscope is  3000 points long if not rapid data collection (600 points).
        """
        # HeNe wavelength/4/avg. num of indices between HeNe peaks

        try:
            if len_waveform != 3000 and len_waveform != 600:
                print("UhOh not the same num of points",
                      len_waveform)  # not always correct number of points if scaling is too small/big
            in_MHz = 300 / one_HeNe_FSR * scale / cal_scale * 3000 / len_waveform
            in_nm = 632 / 4 / one_HeNe_FSR * scale / cal_scale
        except (TypeError, ZeroDivisionError):
            in_MHz = None
            in_nm = None
        return in_MHz, in_nm

    @staticmethod
    def cal_hene(in_MHz, ax, peaks_loc, trigger_data, hene_peak, len_waveform):
        """Calibrates x-axis into nm and changes offset of axis in order to set HeNe peak at 632 nm.
        Turns on axis labels if calibration is completed."""
        if in_MHz is not None and hene_peak is not None:
            ax.xaxis.set_visible(True)  # Turns on x-axis
            peaks_loc_cal = (peaks_loc * in_MHz)  # Converts peak location into MHz
            x_axis_points = in_MHz * np.arange(len_waveform)  # calibrates x-axis points into nm
            x_axis_points_trig = in_MHz * np.arange(len(trigger_data))  # calibrates trigger x-axis into nm
            if hene_peak is None:
                hene_peak_cal = None
            else:
                hene_peak_cal = hene_peak * in_MHz
                HeNeError = (hene_peak_cal - 0)
                x_axis_points = x_axis_points - HeNeError
                peaks_loc_cal = peaks_loc_cal - HeNeError
                hene_peak_cal = hene_peak_cal - HeNeError
                x_axis_points_trig = x_axis_points_trig - HeNeError
        else:
            peaks_loc_cal = peaks_loc
            x_axis_points = np.arange(len_waveform)
            x_axis_points_trig = np.arange(len(trigger_data))
            hene_peak_cal = hene_peak
            ax.xaxis.set_visible(False)

        return x_axis_points, peaks_loc_cal, x_axis_points_trig, hene_peak_cal


##########################################
#  Pop Ups

def no_peaks_check(lost_peaks, window):
    """Pop Up if attempting to lock, but there is an issue with the peaks.
    Yes to continue attempting to lock (will continue when peaks are reestablished),  no to stop locking.
    Will time out and return No automatically after 30 sec.
    """
    if lost_peaks:
        continue_lock = sg.popup_yes_no(
            "Help, I lost the peaks! Should I continue locking?",
            title="Lost Peaks", auto_close=True,
            auto_close_duration=30)
        continue_lock = False if continue_lock == "No" else True
        if not continue_lock:
            window["-LASER-LOCKING-"].click()
    else:
        pass


def check_FSR(one_HeNe_FSR, uncal_sep, scale, rapid_data):
    """Popup to ensure user is ready to set calibration.
    Additional popup if calibration was not successful.
    """
    cal_scale = None
    ready_for_reset = True if sg.popup_yes_no("Are you sure?", title="Calibration Set Up",
                                              modal=False, keep_on_top=True) == "Yes" else False
    if ready_for_reset and uncal_sep != 0 and uncal_sep is not None and not rapid_data:
        one_HeNe_FSR = uncal_sep
        cal_scale = scale
    elif ready_for_reset and (uncal_sep == 0 or uncal_sep is None or rapid_data):
        sg.popup_timed("Calibration set up error, try again. Ensure rapid data is disabled.", auto_close_duration=5)
    else:  # add error if they said yes but something wrong with peaks
        one_HeNe_FSR = None
    return one_HeNe_FSR, cal_scale


def mirror_error_popup():
    """Popup if error in peak identification. Times out after 5 seconds."""
    sg.popup_auto_close(
        "Error in peak identification. Ensure there is only one HeNe peak in FSR and that raspi is connected",
        title="Peak Identification Error",
        modal=False, auto_close_duration=5)


def lock_error_peaks_iden_popup():
    """Pop up if attempted to lock before peaks were correctly identified"""
    sg.popup_auto_close("Peaks not identified. Identify peaks before locking can commence",
                        title="Locking Error",
                        modal=False, auto_close_duration=5)


def lock_error_scale_popup():
    """Pop up if attempted to lock before calibration is complete."""
    sg.popup_auto_close("Please scale x-axis before locking.",
                        title="Locking Error",
                        modal=False, auto_close_duration=5)


##########################################
# CSV

class CSVControls:
    def __init__(self, fname, laser_name=None):
        self.fname = fname
        self.laser_name = laser_name

    def update_defaults(self, default_pos, default_scale, res_rate):
        """Updates values in CSV file if user changes default values. Save rows in CSV, clears CSV and rewrites file with new values"""
        lines = list()
        with open(self.fname, 'r+') as dF:
            writer = csv.writer(dF, delimiter=",")
            reader = csv.reader(dF, delimiter=",")
            for row in reader:
                if row == [] or row is None:
                    pass
                elif row[0] != self.laser_name:
                    lines.append(row)
                else:
                    row[2] = default_pos
                    row[3] = default_scale
                    row[5] = res_rate
                    lines.append(row)
            dF.seek(0)
            dF.truncate()
            for row in lines:
                writer.writerow(row)

    def del_laser(self):
        """Deletes laser from CSV"""
        lines = list()
        with open(self.fname, 'r+') as dF:
            writer = csv.writer(dF, delimiter=",")
            reader = csv.reader(dF, delimiter=",")
            for row in reader:
                if row != [] and row is not None and row[0] != self.laser_name:
                    lines.append(row)
            dF.seek(0)
            dF.truncate()
            for row in lines:
                writer.writerow(row)

    def add_laser_csv(self, new_laser_info):
        """Adds new laser information from dictionary into CSV file"""
        with open(self.fname, 'a') as ld:
            ld.write("\n")
            ld.write(new_laser_info)


def check_entry(laser_name, laser_offset):
    try:
        float(laser_offset)
        if type(laser_name) == str and not str.isspace(laser_name) and laser_name != "" and len(
                laser_name.replace(" ", "")) == len(laser_name):
            if type(laser_offset) == str and not str.isspace(
                    laser_offset) and laser_offset != "" and laser_offset != "0":
                return True
    except:
        return False


def get_laser_info(dict_laser_info):
    laser_name = list(dict_laser_info.keys())[0]  # laser name, defaults to first on csv file
    desired_offset = dict_laser_info[laser_name][0]  # laser offset
    default_pos = dict_laser_info[laser_name][1]  # default pos for default laser
    default_scale = dict_laser_info[laser_name][2]  # default scale for default laser
    return laser_name, desired_offset, default_pos, default_scale


def laser_settings(fname):
    # make dictionary of laser settings saved in a CSV file
    with open(fname, 'r') as ld:
        reader = csv.reader(ld)
        dict_laser_info = OrderedDict(
            {rows[0]: [float(rows[1]), float(rows[2]), float(rows[3]), float(rows[4]), float(rows[5])] for rows in
             reader if
             rows != []})
    return dict_laser_info


correction_array = np.array([])
