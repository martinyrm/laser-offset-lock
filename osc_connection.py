from RsInstrument import *  # RS library for oscilloscope communication. Requires RSVISA application on device


'''Connects to oscilloscope. Only to be run once, at the start of the program'''


# Default position upon start up, reverts to this value upon errors. Will be adjustable by user during program run
# To work continuously, computer sleep timeout must be disabled
# osc IP =  http://142.90.121.229/
# offline lab osc IP = 142.90.106.218

def connect():
    RsInstrument.assert_minimum_version('1.50.0')  # ensure correct version used

    # instrument options
    instr_list = RsInstrument.list_resources('?*', 'rs')
    print(instr_list)

    # connect to oscilloscope
    LanConnect = 'TCPIP::142.90.121.229::inst0::INSTR'  # Instrument address
    if LanConnect not in instr_list:  # check if osc is an option
        exit("Cannot Find Oscilloscope, Try Again")
    instr = RsInstrument(LanConnect, True, False)  # connect
    idn = instr.query_str('*IDN?')  # request ID from oscilloscope (to ensure proper connection)
    # print connected instrument details
    print(f"\nHello, I am: '{idn}'")
    print(f'RsInstrument driver version: {instr.driver_version}')
    print(f'Visa manufacturer: {instr.visa_manufacturer}')
    print(f'Instrument full name: {instr.full_instrument_model_name}')
    print(f'Instrument installed options: {",".join(instr.instrument_options)}')

    # set trigger and acquisition settings in case they were changed on the physical device.
    # currently no way to check that these haven't been changed while the program is running
    instr.write('CHANNEL:AON')
    instr.write('CHANnel1:SCALe 0.05')
    instr.write('CHANnel2:SCALe 10')
    instr.write('TRIGger:A:SOURce CH2')
    instr.write('TRIGger:A:LEVel2 2')
    instr.write('TRIGger:A:MODE NORmal')  # only record when triggered - switch back to NORmal
    instr.write('ACQuire:INTerpolate SMHD')  # data collection as histogram-like so distance between points is const. Doesn't stay constant for all scale ranges!
    instr.write('CHANnel1:DATA:POINts DEFault')
    instr.write("FORM ASCii")
    instr.write('CHANnel1:ARIThmetics AVERage')
    instr.write('ACQuire:AVERage:COUNt 2')
    instr.write('CHANnel1:TYPE PDETect')
    instr.write('ACQuire:WRATe AUTO')  # This is the largest limiting factor for speed. If able to speed up code, remember to update the minimum aed voltage output rate
    instr.write('RUN') # continuous acquisition faster than single acq
    return instr
