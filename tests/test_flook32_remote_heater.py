import importlib.util
import threading
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / 'integrations/flook32/klipper/flook32.py'
spec = importlib.util.spec_from_file_location('ad5x_flook32', MODULE_PATH)
flook32 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flook32)

class FakeGcode:
    def __init__(self): self.mux = []
    def register_mux_command(self, command, key, value, callback, desc=None):
        self.mux.append((command, key, value, callback, desc))

class FakeHeaters:
    def __init__(self):
        self.heaters = {}; self.available_heaters = []; self.registered_sensors = []; self.set_calls = []
    def register_sensor(self, config, obj, gcode_id=None): self.registered_sensors.append((config.get_name(), obj))
    def set_temperature(self, heater, temp, wait=False):
        self.set_calls.append((heater, temp, wait)); heater.set_temp(temp)

class FakePrinter:
    def __init__(self):
        self.gcode = FakeGcode(); self.heaters = FakeHeaters(); self.objects = {}
    def lookup_object(self, name):
        if name == 'gcode': return self.gcode
        if name == 'heaters': return self.heaters
        raise KeyError(name)
    def load_object(self, config, name):
        if name != 'heaters': raise AssertionError(name)
        return self.heaters
    def add_object(self, name, obj):
        if name in self.objects: raise RuntimeError('duplicate object ' + name)
        self.objects[name] = obj
    def command_error(self, message): return RuntimeError(message)

class FakeConfig:
    def __init__(self, printer, values=None): self.printer = printer; self.values = values or {}
    def get_printer(self): return self.printer
    def get_name(self): return 'temperature_sensor chamber'
    def getfloat(self, key, default=None, **kwargs): return float(self.values.get(key, default))
    def error(self, message): return RuntimeError(message)

class FakeSensor:
    def __init__(self):
        self.temp_lock = threading.Lock(); self.air_temp = 24.5; self.heater_temp = 25.5
        self.target_temp = 0.0; self.heater_state = False; self.fan_state = False; self.fan_duty = 0
        self.system_locked = False; self.flook_ip = '192.168.1.230'; self.ws_connected = True
        self.native_heater_enabled = True; self.native_heater_name = 'chamber'
        self.native_heater_max_temp = 65.0; self.native_heater_wait_delta = 2.0
        self.targets = []; self.closed = False
    def set_target_temperature(self, temp):
        self.targets.append(float(temp)); self.target_temp = float(temp); self.heater_state = temp > 0
        return True, None
    def close(self): self.closed = True

def make_heater(values=None):
    printer = FakePrinter(); sensor = FakeSensor()
    if values:
        if 'max_temp' in values: sensor.native_heater_max_temp = float(values['max_temp'])
        if 'wait_delta' in values: sensor.native_heater_wait_delta = float(values['wait_delta'])
    return printer, sensor, flook32.FLOOK32RemoteHeater(FakeConfig(printer, values), sensor, 'chamber')

class RemoteHeaterTests(unittest.TestCase):
    def test_standard_target_command(self):
        printer, sensor, heater = make_heater()
        self.assertTrue(any(x[:3] == ('SET_HEATER_TEMPERATURE', 'HEATER', 'chamber') for x in printer.gcode.mux))
        heater.set_temp(45)
        self.assertEqual(sensor.targets, [45.0])
        self.assertEqual(heater.get_temp(0), (24.5, 45.0))

    def test_fluidd_status_contract(self):
        _, sensor, heater = make_heater(); sensor.target_temp = 48.0; sensor.heater_state = True
        status = heater.get_status(0)
        self.assertEqual(status['temperature'], 24.5)
        self.assertEqual(status['target'], 48.0)
        self.assertEqual(status['power'], 1.0)
        self.assertTrue(status['connected']); self.assertTrue(status['websocket_connected'])

    def test_limits_without_fake_pwm(self):
        _, sensor, heater = make_heater({'max_temp': 65})
        with self.assertRaisesRegex(RuntimeError, 'out of range'): heater.set_temp(66)
        self.assertEqual(sensor.targets, [])
        remote = MODULE_PATH.read_text(encoding='utf-8').split('class FLOOK32RemoteHeater:', 1)[1]
        self.assertNotIn('heater_pin', remote); self.assertNotIn('setup_pin', remote); self.assertNotIn('set_pwm', remote)

    def test_wait_and_turn_off(self):
        _, sensor, heater = make_heater({'wait_delta': 2}); sensor.target_temp = 45; sensor.air_temp = 40
        self.assertTrue(heater.check_busy(0)); sensor.air_temp = 43; self.assertFalse(heater.check_busy(0))
        heater.set_temp(0); self.assertEqual(sensor.targets[-1], 0.0)


    def test_failed_remote_off_does_not_block_global_shutdown(self):
        _, sensor, heater = make_heater()
        sensor.target_temp = 45.0
        sensor.heater_state = True
        sensor.set_target_temperature = lambda temp: (False, 'offline')
        heater.set_temp(0)
        self.assertEqual(sensor.target_temp, 0.0)
        self.assertFalse(sensor.heater_state)

    def test_failed_remote_heat_request_is_an_error(self):
        _, sensor, heater = make_heater()
        sensor.set_target_temperature = lambda temp: (False, 'offline')
        with self.assertRaisesRegex(RuntimeError, 'offline'):
            heater.set_temp(45)

    def test_existing_sensor_registers_native_heater_proxy(self):
        printer = FakePrinter(); config = FakeConfig(printer); sensor = FakeSensor()
        heater = flook32._register_remote_heater(config, sensor)
        self.assertIs(printer.heaters.heaters['chamber'], heater)
        self.assertEqual(printer.heaters.available_heaters, ['heater_generic chamber'])
        self.assertIs(printer.objects['heater_generic chamber'], heater)
        self.assertEqual(printer.heaters.registered_sensors, [])

    def test_hidden_sensor_gets_clean_native_heater_name(self):
        self.assertEqual(
            flook32._native_heater_default_name('_flook32_chamber'),
            'chamber')
        self.assertEqual(
            flook32._native_heater_default_name('chamber'),
            'chamber')

    def test_native_heater_can_be_disabled(self):
        printer = FakePrinter(); config = FakeConfig(printer); sensor = FakeSensor()
        sensor.native_heater_enabled = False
        self.assertIsNone(flook32._register_remote_heater(config, sensor))
        self.assertEqual(printer.heaters.available_heaters, [])

if __name__ == '__main__': unittest.main()
