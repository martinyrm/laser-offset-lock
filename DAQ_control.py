from mcculw import ul
from mcculw.enums import InterfaceType
from mcculw.device_info import DaqDeviceInfo
from mcculw.enums import DigitalIODirection
from mcculw.device_info import DioInfo
from mcculw.ul import ULError


class DAQ:

    output_range = None
    ao_device = None
    daq_device = None

    def __init__(self):
        pass

    @staticmethod
    def DAQconnect():
        """Connects to DAQ. Based on Output Analog example code from MCC. Currently, set up for USB DAQ.
        Can connect to ethernet DAQ by changing connection code, may need other software /code to connect to IP."""
        output_channel = 0
        interface_type = InterfaceType.ANY
        try:
            # Get descriptors for all the available DAQ devices.
            devices = ul.get_daq_device_inventory(interface_type)
            number_of_devices = len(devices)

            # Verify at least one DAQ device is detected.
            if number_of_devices == 0:
                raise RuntimeError('Error: No DAQ device is detected')

            print('Found', number_of_devices, 'DAQ device(s):')
            for i in range(number_of_devices):
                print('  [', i, '] ', devices[i].product_name, ' (',
                      devices[i].unique_id, ')', sep='')
            DAQ.board_num = 1
            if DAQ.board_num not in range(number_of_devices):
                raise RuntimeError('Error: Invalid descriptor index')
            print('here')
            # Create the DAQ device from the descriptor at the specified index.
            #ul.create_daq_device(DAQ.board_num, devices[DAQ.board_num])
            daq_dev_info = DaqDeviceInfo(DAQ.board_num)
            dio_info = daq_dev_info.get_dio_info()
            if not daq_dev_info.supports_analog_output:
                raise Exception('Error: The connected device does not support analog output. Please check device connection or the value of DAQ.board_num in DAQ_control.py')
            
            ao_info = daq_dev_info.get_ao_info()
            if not daq_dev_info.supports_digital_io:
                raise Exception('Error: The DAQ device does not support '
                                'digital I/O')
            global port
            port = next((port for port in dio_info.port_info if port.supports_output),
                        None)
            if not port:
                raise Exception('Error: The DAQ device does not support '
                                'digital output')

            ul.d_config_port(DAQ.board_num, port.type, DigitalIODirection.OUT)
            print(port.type)
            DAQ.output_range = ao_info.supported_ranges[0]
            print('here2')
            print('    Function demonstrated: AoDevice.a_out')
            print('    Channel: ',  output_channel)
            print('    Range:', DAQ.output_range.name)


        except RuntimeError as error:
            print('\n', error)
            DAQ.output_range = None

    @staticmethod
    def daq_output(correction):
        """Outputs calculated voltage to DAQ channel VOUT0"""
        try:
            # try:s
            output_channel = 0
            out_val = ul.from_eng_units(DAQ.board_num,DAQ.output_range, correction)

            ul.a_out(DAQ.board_num, output_channel, DAQ.output_range, out_val)
        # except (ValueError, NameError, SyntaxError, AttributeError):
        #    pass
        except KeyboardInterrupt:
            pass
    @staticmethod
    def daq_mirror_flipper_on():
            ul.d_out(DAQ.board_num, port.type, 0xFF)
            print('up daq')
    @staticmethod
    def daq_mirror_flipper_off():
            ul.d_out(DAQ.board_num, port.type, 0x00)
            print('down daq')
    @staticmethod
    def daq_disconnect():
        """Disconnects from DAQ device"""
        DAQ().daq_output(0)
        if DAQ.daq_device is not None:
            # Disconnect from the DAQ device.
            if DAQ.daq_device.is_connected():
                DAQ.daq_device.disconnect()
            # Release the DAQ device resource.
            DAQ.daq_device.release()
