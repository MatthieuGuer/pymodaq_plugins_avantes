import numpy as np
from pymodaq.utils.daq_utils import ThreadCommand
from pymodaq.utils.data import DataFromPlugins, Axis, DataToExport, DataRaw
from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, \
    comon_parameters, main
from pymodaq.utils.parameter import Parameter
from pymodaq_plugins_avantes.hardware.AvaSpec_Controller \
    import AvantesController, get_devices_list
from scipy.interpolate import interp1d
from pymodaq_utils.logger import set_logger, get_module_name
logger = set_logger(get_module_name(__file__))

class DAQ_1DViewer_Avantes(DAQ_Viewer_base):
    """ Avantes Spectrometer Instrument plugin class for a 1D viewer.
    Besides acquiring spectral data, the Avantes device may control ten digital
    output lines. They are exposed to PyMoDAQ as parameters. Acquisition on
    digital and analog input lines is not yet supported.
    """

    # define controller type for easy autocompletion
    controller_type = AvantesController
    serials = get_devices_list()

    params = comon_parameters+[
        {'title': 'Spectrometer settings:', 'name': 'spectrometer_settings',
         'type': 'group', 'children':[
            {'title': 'Integration time [ms]:', 'name': 'integration_time',
            'type': 'float', 'min': 0.001, 'value': 100,
            'tip': 'Integration time in milliseconds'},
            {'title': 'Start pixel:', 'name': 'start_pixel',
            'type': 'int', 'min': 0, 'max':4094, 'value': 0},
            {'title': 'Stop pixel:', 'name': 'stop_pixel',
            'type': 'int', 'min': 1, 'max':4095, 'value': 4093},
            {'title': 'Average:', 'name': 'number_average',
            'type': 'int', 'min': 1, 'value': 1,
            'tip': 'Not working yet'},
            {'title': 'Device list', 'name': 'device_list',
                'type': 'list', 'limits': serials},
            {'title': 'Sensitivity:', 'name': 'sensitivity',
                'type': 'list', 'limits': ["None", "Low noise", "High sensitivity"], 'value':"None"},
            {'title': 'High resolution:', 'name': 'high_resolution',
                'type': 'bool', 'value': True, 'tip': '14 or 16 bit'},
            {'title': 'Timestamp:', 'name': 'timestamp',
            'type': 'bool', 'value': False, 'tip': 'Also returns a timestamp'},
            # { 'title': 'X-Axis in wavenumbers:', 'name': 'wavenumber',
            # 'type': 'bool', 'value': False },
        ]},
        {'title': 'Trigger settings:', 'name': 'trigger_settings',
         'type': 'group', 'children':[
            {'title': 'Burst mode:', 'name': 'burst_mode',
            'type': 'bool', 'value':False},
            {'title': 'Shot number:', 'name': 'shot_number',
            'type': 'int', 'value':10, 'min':2, 'visible':False},
            {'title': 'Trigger mode:', 'name': 'trigger_mode',
            'type': 'list', 'limits': ["Software", "Hardware", "Single scan"], 'value':"Software"},
            #Single scan only for AS7010 and AS5216 (with custom firmware), not implemented yet
            {'title': 'Trigger Source:', 'name': 'trigger_source',
            'type': 'list', 'limits':["External", "Synchronized"], 'visible':False},
            # Synchronized not implemented yet but I added it anyway
            {'title': 'Trigger type:', 'name': 'trigger_type',
            'type': 'list', 'limits':["Edge", "Level"], 'visible':False},
            #Level type only for AS5216 and AS7010, not implemented yet
         ]},
        {'title': 'Calibration settings:', 'name': 'calibration_settings',
         'type': 'group', 'children':[
            {'title': 'Calibration:', 'name': 'calibration',
            'type': 'bool', 'value': False},
            {'title': 'Calibration File:', 'name': 'calibration_file',
            'type': 'file', 'tip':'Calibration file'},
         ]},

        {'title': 'Digital outputs', 'name': 'digital_outputs',
         'type': 'group', 'expanded':False, 'children': [
            {'title': 'Output %d:' % (i + 1), 'name': 'output_%d' % (i + 1),
            'type': 'led_push', 'value': False, 'tip': 'Logic level on output %d' % (i + 1)} 
            for i in range(10)
        ]},

    ]

    def ini_attributes(self):
        self.controller: self.controller_type = None
        self.x_axis = None
        self.timestamp = False
        self.serial_number = self.settings.child('spectrometer_settings', 'device_list').value()
        get_devices_list()  #needed if we close and open again, because of AVS_Done()
        self.calibration_func = lambda x:1
        self.burst_mode = self.settings.child('trigger_settings', 'burst_mode').value()
        self.shot_number = self.settings.child('trigger_settings', 'shot_number').value()
        
    def commit_settings(self, param: Parameter):
        if param.name() == "integration_time":
            self.controller.set_integration_time(param.value())
        elif param.name() in ["start_pixel", "stop_pixel"]:
            self.controller.set_pixel_range(
                self.settings.child('spectrometer_settings', 'start_pixel').value(),
                self.settings.child('spectrometer_settings', 'stop_pixel').value()
            )
            self.init_axis()

        elif param.name() == "number_average":
            self.controller.set_number_of_averages(param.value())
        elif param.name() == "timestamp":
            self.timestamp = param.value()
        elif param.name() == "sensitivity":
            self.controller.set_sensitivity_mode(param.value())
        elif param.name() == "high_resolution":
            self.controller.set_resolution(param.value())
        elif param.name() == "calibration_file":
            self.make_calib_curve(param.value())
            self.calibration_curve = self.calibration_func(self.controller.wavelengths)
        elif param.name() == "burst_mode":
            self.burst_mode = param.value()
            self.settings.child('trigger_settings', 'shot_number').setOpts(visible=param.value())
            if self.burst_mode:
                self.shot_number = self.settings.child('trigger_settings', 'shot_number').value()
            else:
                self.shot_number = 1
            self.init_axis()
        elif param.name() == "shot_number":
            self.shot_number = param.value()

        elif param.name() == "trigger_mode":
            # if param.value() == "Software":
            #     # self.settings.child('trigger_settings', 'trigger_source').setOpts(visible=False)
            #     # self.settings.child('trigger_settings', 'trigger_type').setOpts(visible=False)
            # else:
            #     # self.settings.child('trigger_settings', 'trigger_source').setOpts(visible=True)
            #     # self.settings.child('trigger_settings', 'trigger_type').setOpts(visible=True)
            self.controller.set_trigger_mode(mode=param.value())

        elif param.name()[:7] == 'output_':
            # Note: digital outputs are not really parameters. However and
            # for the time being, this seems to come closest to PyMoDAQ's
            # functionallity.
            self.controller.set_digital_output(int(param.name()[7:]),
                                               param.value())

    def ini_detector(self, controller=None):
        """Detector communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only 
            one actuator/detector by controller
            (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        self.ini_detector_init(slave_controller=controller)

        if self.is_master:
            self.controller = self.controller_type()
            # if self.controller.open_communication(self.devices[self.serial_number]):
            if self.controller.open_communication(self.serial_number):
                info = "Avantes Spectro initilialized"
            else:
                info = "Avantes initialisation failed"
                return info, False
            
            self.controller.set_pixel_range(
                self.settings.child('spectrometer_settings', 'start_pixel').value(),
                self.settings.child('spectrometer_settings', 'stop_pixel').value()
            )
            self.init_axis()

            self.controller.set_default_config()
        else:
            self.controller = controller

        if self.settings.child('spectrometer_settings', 'high_resolution').value():
            self.controller.set_resolution(True)
        self.controller.set_sensitivity_mode(self.settings.child('spectrometer_settings', 'sensitivity').value())
        self.controller.set_trigger_mode(mode=self.settings.child('trigger_settings', 'trigger_mode').value())
        initialized = True
        return info, initialized

    def init_axis(self):
        wavelengths = self.controller.wavelengths
        if not self.burst_mode:
            self.x_axis = Axis(label='Wavelength', units='nm',
                                data=wavelengths)
            dfp = DataFromPlugins(name='Avantes',
                                    data=[np.zeros(len(wavelengths))],
                                    dim='Data1D', axes=[self.x_axis],
                                    labels=['Avantes-Signal'])

        else:
            N = int(self.shot_number)
            self.x_axis = Axis(label='Wavelength', units='nm',
                                data=wavelengths)
            shot_axis = Axis(label='Shot #', units='', data=np.arange(N))

            dfp = DataFromPlugins(name='Avantes',
                                    data=[np.random.random((N, len(wavelengths)))],
                                    dim='Data2D',
                                    axes=[shot_axis, self.x_axis],
                                    # nav_indexes=(0,),
                                    labels=['Avantes-Burst'])
        self.calibration_curve = self.calibration_func(self.controller.wavelengths)
        self.dte_signal_temp.emit(DataToExport(name='Avantes', data=[dfp]))

    def close(self):
        """Terminate the communication protocol"""

        self.controller.close_communication()
        self.controller = None
        # initialized = False
        # return initialized    
        # This return makes pmd crash when closing + reopening

    def grab_data(self, Naverage=1, **kwargs):
        """Start grabbing from the detector
        Use a synchrone acquisition (blocking function)

        Parameters
        ----------
        Naverage: int
            Number of hardware averaging.
        """
        if not self.burst_mode:
            data,timestamp = self.controller.grab_spectrum()
            if self.settings.child("calibration_settings", "calibration").value():
                data /= self.calibration_curve

            dfp = DataFromPlugins(name='Avantes', data=data, dim='Data1D',
                                labels=['data'], axes=[self.x_axis])

            if self.timestamp:
                dwa0D_timestamp = DataRaw('timestamp', units='dimensionless',
                                            data=np.array([timestamp]))
                self.dte_signal.emit(DataToExport(name='spectrum',
                                                data= [dfp, dwa0D_timestamp]))
            else:
                self.dte_signal.emit(DataToExport(name='spectrum', data= [dfp]))
        else:
            N = int(self.shot_number)
            data, _ = self.controller.grab_spectrum(N=N)
            shot_axis = Axis(label='Shot #', units='', data=np.arange(N))
            dfp = DataFromPlugins(name='Avantes',
                        data=[data],
                        dim='Data2D',
                        axes=[shot_axis, self.x_axis],
                        # nav_indexes=(0,),
                        labels=['Avantes-Burst'])

            self.dte_signal.emit(DataToExport(name='Avantes', data= [dfp]))

 
    def stop(self):
        self.controller.abort_measurement()

    def has_dark_shutter(self):
        return False

    def has_reference_shutter(self):
        return False

    def make_calib_curve(self, fpath):
        try:
            calibdat = np.loadtxt(fpath)
            λcalib = calibdat[:, 0]
            logger.info(f"Calibration is defined from {λcalib[0]:.2f}nm to {λcalib[-1]:.2f}nm")

            calibfac = calibdat[:, 1]
            self.calibration_func = interp1d(λcalib, calibfac, kind="cubic", fill_value="extrapolate")
        except:
            self.calibration_func = lambda x:1
            print("Bad calibration file")

if __name__ == '__main__':
    main(__file__)
