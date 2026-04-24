import time,sys
import numpy as np
from datetime import datetime
from enum import Enum
from pymodaq_plugins_avantes.hardware import avaspec

class AvsDeviceType(Enum):

    UNKNKOWN = 0
    AS5216 = 1
    ASMINI = 2
    AS7010 = 3
    AS7007 = 4




def get_devices_list():
    """ Get the devices connected and their serial number.
    
    Returns
    -------
    serial_numbers : list of str
    # device_dict : dict of devices object indexed by serial number
    """
    device_nb = avaspec.AVS_Init(-1)

    if device_nb > 0:
        device_list = avaspec.AVS_GetList()
        serial_numbers = [f"{device.SerialNumber.decode("utf-8")}" for device in device_list]
        # return(serial_numbers, {serial_numbers[i]:device_list[i] for i in range(len(serial_numbers))})
        return serial_numbers
    # return([], {})
    return([])


class AvantesController:
    """
    Controller for the Avantes Spectrometer AvaSPec-ULS2048CL-EVO
    This class relies on communication with the instrument via USB-3 link

    Additional methods provide control over digital output and analog input
    See Avantes doc. and avaspec.py module
    Remark:
            - The AVS spectrometer functions are managed over 4096 pixels even
              though the spectrometer has only 2048 pixels.
            - Only a single USB spectrometer is controlled.
            - For asynchronous measurement with callback function, see either
              AvantesControllerTestApp.py or PyQt5_demo.py
    """

    def __init__(self):
        """
        Method called at object creation (implementation)
        Init object attributes
        """

        self._initialized = False
        self.hardware_present = False
        self._serial_number = str("none")
        self._measurement_config = avaspec.MeasConfigType()
        self._device_handle = 0
        self._number_of_pixels = 4096
        self._wavelengths = [0.0] * 4096
        self._spectraldata = [0.0] * 4096
        self.start_pixel = 0
        self.stop_pixel = self._number_of_pixels - 1
        self._scan_count = 0
        # shouldn't this go to the PyMoDAQ parameters?
        self._integration_time = 100

    # def open_communication(self, device) -> bool:
    def open_communication(self, serial_number) -> bool:
        """
        Open the USB communication with an Avantes Spectrometer

        Returns
        -------
                True on succes, else False
        """
        if avaspec.lib is None:
            return False

        # self._serial_number = str(device.SerialNumber.decode("utf-8"))
        self._serial_number = serial_number
        self._initialized = True

        # Activate spectrometer for communication and get a handle on it
        # self._device_handle = avaspec.AVS_Activate(device)
        self._device_handle = avaspec.AVS_GetHandleFromSerial(serial_number)

        # Get device configuration (number of pixels and wavelength)
        device_config = avaspec.AVS_GetParameter(self._device_handle, 63484)

        self._number_of_pixels = device_config.m_Detector_m_NrPixels

        self._full_wavelength = avaspec.AVS_GetLambda(self._device_handle)
        self._wavelengths = self._full_wavelength[self.start_pixel:self.stop_pixel]
        #devicetype = avaspec.AVS_GetDeviceType(globals_var.dev_handle)

        self.hardware_present = True
        return True

    @property
    def is_initialized(self) -> bool:
        """
        Check if the controller is initialized

        Returns
        -------
                the initialized status True of False
        """
        return self._initialized

    @property
    def serial_number(self) -> str:
        """
        Get the serial number of the Avantes

        Returns
        -------
                serial number (str)
        """
        return self._serial_number

    def close_communication(self):
        """
        Close communication
        """
        ret = avaspec.AVS_Deactivate(self._device_handle)
        if ret:
            print('Successfully closed ' + self.serial_number)
        else:
            self.print_error_message(ret)

        avaspec.AVS_Done()
        #If using this AVS_Done, need to call again the AVS_Init() to open another device

    def set_default_config(self):
        """
        Configure the acquisition using the _measconfig object using
        default parameters and send the configuration to the spectrometer
        """
        self.print_error_message(avaspec.AVS_UseHighResAdc(self._device_handle, True))

        self._measurement_config.m_IntegrationTime = self._integration_time # in ms
        self._measurement_config.m_IntegrationDelay = 0
        self._measurement_config.m_NrAverages = 1
        self._measurement_config.m_CorDynDark_m_Enable = 0
        # nesting of types does NOT work!! ?? whatever that means
        self._measurement_config.m_CorDynDark_m_ForgetPercentage = 0
        self._measurement_config.m_Smoothing_m_SmoothPix = 0
        self._measurement_config.m_Smoothing_m_SmoothModel = 0
        self._measurement_config.m_SaturationDetection = 0
        self._measurement_config.m_Trigger_m_Mode = 0
        self._measurement_config.m_Trigger_m_Source = 0
        self._measurement_config.m_Trigger_m_SourceType = 0
        self._measurement_config.m_Control_m_StrobeControl = 0
        self._measurement_config.m_Control_m_LaserDelay = 0
        self._measurement_config.m_Control_m_LaserWidth = 0
        self._measurement_config.m_Control_m_LaserWaveLength = 0.0
        self._measurement_config.m_Control_m_StoreToRam = 0

        self._prepare_mesure()

        # measurement counter
        self._scan_count = 0

        time.sleep(0.001)

    def _prepare_mesure(self):
        ret = avaspec.AVS_PrepareMeasure(self._device_handle, self._measurement_config)
        self.print_error_message(ret)

    def set_integration_time(self, integration_time: float):
        """
        Set the integration time in [ms]

        Parameter
        ---------
                integration_time in [ms]
        """
        self._measurement_config.m_IntegrationTime = float(integration_time)
        self._prepare_mesure()
        self._integration_time = integration_time


    def set_pixel_range(self, start_pixel, stop_pixel):
        print(f"Setting the range from {self._full_wavelength[start_pixel]:.2f} to {self._full_wavelength[stop_pixel]:.2f}")
        self.start_pixel = start_pixel
        self.stop_pixel  = stop_pixel
        self._measurement_config.m_StartPixel = start_pixel
        self._measurement_config.m_StopPixel  = stop_pixel
        self._prepare_mesure()

        
    def set_number_of_averages(self, n_average: int):
        """
        Set the number of average

        Parameter
        ---------
                average_nb
        """
        print(f"Number of averages set to {n_average}.")
        self._measurement_config.m_NrAverages = n_average
        self._prepare_mesure()

    def set_resolution(self, high_res=False):
        ret = avaspec.AVS_UseHighResAdc(self._device_handle, high_res)
        self.print_error_message(ret)
        self._prepare_mesure()

    def set_sensitivity_mode(self, mode="Low noise"):
        """ 0 > low noise, 1 > high sensitivity """
        if mode == "None":
            return
        elif mode == "Low Noise":
            m = 0
        else:
            m = 1
        ret = avaspec.AVS_SetSensitivityMode(self._device_handle, m)
        self.print_error_message(ret)
        self._prepare_mesure()

    def set_trigger_mode(self, mode="Software"):
        if mode == "Software":
            self._measurement_config.m_Trigger_m_Mode = 0
        elif mode == "Hardware":
            self._measurement_config.m_Trigger_m_Mode = 1
        self._measurement_config.m_Trigger_m_Source = 0     #Not implemented yet
        self._measurement_config.m_Trigger_m_SourceType = 0 #Not implemented yet


    def get_digital_input(self, pin_no: int) -> int:
        """
        Returns the status of the specified digital input

        Parameters
        ----------
            portId
            For the AS7010:
            0 = DI1 = Pin 24 at 26-pins connector
            1 = DI2 = Pin 7 at 26-pins connector
            2 = DI3 = Pin 16 at 26-pins

        Returns
        -------
                digital state 0=low or 1=high
        """

        return avaspec.AVS_GetDigIn(self._device_handle, pin_no)

    def set_digital_output(self, pin_no: int, value: int) -> int:
        """
        Set the digital output value for the specified digital output

        Parameters
        ----------
            portId
            For the AS7010:
            0 = DO1 = pin 11 at 26 - pins connector (can be used also as PWM)
            1 = DO2 = pin 2 at 26 - pins connector (can be used also as PWM)
            2 = DO3 = pin 20 at 26 - pins connector (can be used also as PWM)
            3 = DO4 = pin 12 at 26 - pins connector
            4 = DO5 = pin 3 at 26 - pins connector (can be used also as PWM)
            5 = DO6 = pin 21 at 26 - pins connector (can be used also as PWM)
            6 = DO7 = pin 13 at 26 - pins connector (can be used also as PWM)
            7 = DO8 = pin 4 at 26 - pins connector
            8 = DO9 = pin 22 at 26 - pins connector
            9 = DO10 = pin 25 at 26 - pins connector

            value: 0 (low) or 1 (high)

        Returns
        -------
                On success:    0   = ERR_SUCCESS
                On error:      -3  = ERR_DEVICE_NOT_FOUND
                               -28 = ERR_INVALID_DEVICE_ID
                               -6  = ERR_TIMEOUT (error in communication)
                               -1  = ERR_INVALID_PARAMETER
        """

        return avaspec.AVS_SetDigOut(self._device_handle, pin_no, value)

    def set_analog_output(self, pin_no: int, value: float) -> int:
        """
        Set the analog output value for the specified digital output

        Parameters
        ----------
            portId:
            For the AS7010:
            0 = AO1 = pin 17 at 26 - pins connector
            1 = AO2 = pin 26 at 26 - pins connector

            value: 0 or 5.0 V

        Returns
        -------
                On success:    0   = ERR_SUCCESS
                On error:      -3  = ERR_DEVICE_NOT_FOUND
                               -28 = ERR_INVALID_DEVICE_ID
                               -6  = ERR_TIMEOUT (error in communication)
                               -1  = ERR_INVALID_PARAMETER
        """
        return avaspec.AVS_SetAnalogOut(self._device_handle, pin_no, value)

    @property
    def wavelengths(self):
        """
        Get an array of wavelength used by the spectrometer
        Returns
        -------
                a "standard" array of 4096 elements whom, in case of a
                Avaspec-ULS2048CL-EVO, 2048 has wavelength number,
                other elements are set to zeros  !!!
        """

        self._full_wavelength = avaspec.AVS_GetLambda(self._device_handle)
        # return np.array_split(np.array(full_scale), 2)[0]
        return np.array(self._full_wavelength)[self.start_pixel:self.stop_pixel]

    def grab_spectrum(self, N=1):
        """
        Read the spectrum from the Avantes Spectrometer
        And store result in global_vars.spectrometer_y_values

        Returns
        -------
                none, only update globals_vars
        """

        if N > 1:
            self._measurement_config.m_Control_m_StoreToRam = N
        self._prepare_mesure()

        ret = avaspec.AVS_Measure(self._device_handle, 0, 1)
        self.print_error_message(ret)

        measurement_time = N*self._measurement_config.m_IntegrationTime/1000 #in seconds
        start_time = time.time()
        done = False
        time.sleep(measurement_time) # at least wait for the integration time !
    
        while not done and time.time() -start_time < 10*measurement_time:
            done = bool(avaspec.AVS_PollScan(self._device_handle))
        if done:
            if N == 1:
                timestamp, data = avaspec.AVS_GetScopeData(self._device_handle)
                spectra = np.array(data)[:-self.start_pixel+self.stop_pixel]
            else:
                spectra = np.empty((N, len(self.wavelengths)))
                timestamp = []
                for i in range(N):
                    timestamp_i, data = avaspec.AVS_GetScopeData(self._device_handle)
                    spectra[i,:] = np.array(data)[:-self.start_pixel+self.stop_pixel]
                    timestamp.append(timestamp_i)

            self._scan_count += 1
            # time.sleep(0.001)
            self._measurement_config.m_Control_m_StoreToRam = 0
            return spectra, timestamp
        else:
            print("Measurement timed out")
            self.print_error_message(self.abort_measurement())

    def abort_measurement(self):
        """
        Abort a running measurement

        Returns
        -------
                SUCCESS = 0 or FAILURE <> 0
        """
        # self._is_grabbing = False
        return avaspec.AVS_StopMeasure(self._device_handle)

    def start_continuous_grabbing(self, callback):
        print("controller start grabbing")
        self.pymodaq_callback = callback
        avs_cb = avaspec.AVS_MeasureCallbackFunc(self.avantes_callback)
        self._scan_count = 0
        avaspec.AVS_MeasureCallback(self._device_handle, avs_cb, -1)
        time.sleep(0.1)

    def avantes_callback(self, lparam1, lparam2):
        """
        Retrieve the spectrum from the Avantes Spectrometer
        Use this function in an asynchrone "callback" mechanism

        Returns
        -------
                spectraData: a tuple: timestamp, array of 4096 double
        """
        result = avaspec.AVS_GetScopeData(self._device_handle)
        full_data = np.array(result[1])
        self._scan_count += 1
        self.pymodaq_callback(np.array_split(full_data, 2)[0])


    error_message_dict = {
        0: "Operation succeeded",
        -1: " Function called with invalid parameter value.",
        -2: " e.g. Function called to use 16bit ADC mode, with 14bit ADC hardware",
        -3: "Opening communication failed or time-out during communication occurred.",
        -4: "AvsHandle is unknown in the DLL",
        -5: "Function is called while result of previous call to AVS_Measure() is not received yet",
        -6: "No answer received from device",
        -7: "-",
        -8: "No measurement data is received at the point AVS_GetScopeData() is called",
        -9: "Allocated buffer size too small",
        -10: "Measurement preparation failed because pixel range is invalid",
        -11: "Measurement preparation failed because integration time is invalid (for selected sensor)",
        -12: "Measurement preparation failed because of an invalid combination of parameters",
        -13: "-",
        -14: "Measurement preparation failed because no measurement buffers available",
        -15: "Unknown error reason received from spectrometer",
        -16: "Error in communication or Ethernet connection failure",
        -17: "No more spectra available in RAM, all read or measurement not started yet",
        -18: "DLL version information could not be retrieved",
        -19: "Memory allocation error in the DLL",
        -20: "Function called before AVS_Init() is called",
        -21: "Function failed because AvaSpec is in wrong state (e.g. AVS_Measure() without calling AVS_PrepareMeasurement() first)",
        -22: " Reply is not a recognized protocol message",
        -23: "-",
        -24: "Error occurred while opening a bus device on the host. E.g. USB device access denied due to user rights",
        -25: "A read error has occurred. Spectrometer has failed when reading, for example, the Device Configuration settings from the internal flash memory",
        -26: "A write error has occurred. Spectrometer has failed when writing, for example, the Device Configuration settings into the internal flash memory",
        -27: "DLL could not be initialized due to an Ethernet connection initialization error which is caused by the presence of another DLL instance running on the same machine. It also could have been caused by calling the AVS_Init() function too quickly after calling AVS_Done(). In case of ERR_ETHCONN_REUSE, AVS_Init() can be invoked again to retry the initialization.",
        -100: "NrOfPixel in Device data incorrect",
        -101: "Gain Setting out of range",
        -102: "Offset Setting out of range",
        -110: "Use of Saturation Detection Level 2 is not compatible with the Averaging function ",
        -111: "Use of Averaging is not compatible with the StoreToRam function ",
        -112: "Use of the Synchronize setting is not compatible with the StoreToRam function",
        -113: "Use of Level Triggering is not compatible with the StoreToRam function",
        -114: "Use of Saturation Detection Level 2 Parameter is not compatible with the StoreToRam function",
        -115: "The StoreToRam function is only supported with firmware version 0.20.0.0 or later.",
        -116: "Dynamic Dark Correction not supported",
        -120: "Use of AVS_SetSensitivityMode() not supported by detector type",
        -121: "Use of AVS_SetSensitivityMode() not supported by firmware version",
        -122: "Use of AVS_SetSensitivityMode() not supported by FPGA version",
        -140: "Spectrometer was not calibrated for stray light correction",
        -141: "Incorrect start pixel found in EEPROM",
        -142: "Incorrect end pixel found in EEPROM",
        -143: "Incorrect start or end pixel found in EEPROM",
        -144: "Factor should be in range 0.0 – 4.0",
    }


    def print_error_message(self, err_nb):
        if err_nb < 0:
            try:
                print(f"{self.error_message_dict[err_nb]}")
            except KeyError:
                print("Unknown error ?")


### simulating non existing device for debugging purpose

# PIN_SIGNAL     = 2
# PIN_REFERENCE  = 6
# PIN_AVALIGHT   = 3
# PIN_EXCITATION = 9


class AvantesSimuController(AvantesController):
    """Simulates data in case no spectrometer is connected."""

    def __init__(self, initial_line_states=0):
        AvantesController.__init__(self)
        self._pin_states = [initial_line_states for _ in range(10)]
        self._signal = 3000 * np.exp(-((self.wavelengths - 600) / 300)**4)
        self._induced = np.exp(-((self.wavelengths - 400) / 30)**2)
        self._reference = 3500 * np.exp(-((self._wavelengths - 600) / 300)**4)

    def open_communication(self):
        self._pin_states[PIN_AVALIGHT-1]   = 1
        self._pin_states[PIN_SIGNAL-1]     = 1
        self._pin_states[PIN_REFERENCE-1]  = 0
        self._pin_states[PIN_EXCITATION-1] = 1
        return True

    @staticmethod
    def close_communication():
        pass

    def configure_acquisition_by_default(self):
        pass

    def set_integration_time(self, integration_time: int):
        """
        Set the integration time in [ms]

        Parameter
        ---------
                integration_time in [ms]
        """
        self._measurement_config.m_IntegrationTime = float(integration_time)

    def set_number_of_averages(self, n_average: int):
        """
        Set the number of average

        Parameter
        ---------
                average_nb
        """
        self._measurement_config.m_NrAverages = n_average

    def get_digital_input(self, pin_no: int) -> int:
        return 0

    def set_digital_output(self, pin_no: int, value: int) -> int:
        self._pin_states[pin_no - 1] = value
        return 0

    def set_analog_output(self, pin_no: int, value: float) -> int:
        return 0

    @property
    def wavelengths(self):
        """
        Get an array of wavelength used by the spectrometer
        Returns
        -------
                a "standard" array of 4096 elements whom, in case of a
                Avaspec-ULS2048CL-EVO, 2048 has wavelength number,
                other elements are set to zeros  !!!
        """

        self._wavelengths = np.linspace(300, 900, 2048)
        return self._wavelengths

    def grab_spectrum(self):
        """
        Read the spectrum from the Avantes Spectrometer
        And store result in global_vars.spectrometer_y_values

        Returns
        -------
                none, only update globals_vars
        """
        now = time.time()
        if not hasattr(self, "start_time"):
            self.start_time = now
        drift = 1 + 0.1 * np.sin(now / 20 * 2 * np.pi)

        signal = np.random.normal(120, 4, 2048) #\
#            * (1 + 0.1 * np.sin(now / 60 * 2 * np.pi))

        if self._pin_states[PIN_AVALIGHT - 1] == 0:
            return signal, time.time()

        if self._pin_states[PIN_SIGNAL - 1] == 1:
            if self._pin_states[PIN_EXCITATION - 1] == 0:
                signal += np.random.normal(self._signal * drift, 20)
            else:
                kinetics = np.exp(-(now - self.start_time) / 120)
                signal += \
                    np.random.normal(self._signal * drift \
                                    * (1 - 0.1 * (1 - kinetics) * self._induced),
                                     20)

        if self._pin_states[PIN_REFERENCE - 1] == 1:
            signal += np.random.normal(self._reference * drift, 20)

        return signal, time.time()

    def abort_measurement(self):
        """
        Abort a running measurement

        Returns
        -------
                SUCCESS = 0 or FAILURE <> 
        """
        pass
