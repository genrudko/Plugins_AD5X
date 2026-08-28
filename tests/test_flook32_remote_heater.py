import importlib.util
import threading
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / 'integrations/flook32/klipper/flook32.py'
spec = importlib.util.spec_from_file_location('ad5x_flook32', MODULE_PATH)
flook32 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flook32)

class FakeGcode:
    def __init__(self):
        self.mux = []
        self.commands = {}
        self.ready_gcode_handlers = self.commands
    def register_mux_command(self, command, key, value, callback, desc=None):
        self.mux.append((command, key, value, callback, desc))
    def register_command(self, command, callback, when_not_ready=False, desc=None):
        if command in self.commands:
            raise RuntimeError('duplicate command ' + command)
        self.commands[command] = callback

class FakeHeaters:
    cmd_TEMPERATURE_WAIT_help = 'Wait for temperature'
    def __init__(self):
        self.heaters = {}; self.available_heaters = []; self.available_sensors = []; self.registered_sensors = []; self.set_calls = []
    def register_sensor(self, config, obj, gcode_id=None): self.registered_sensors.append((config.get_name(), obj))
    def set_temperature(self, heater, temp, wait=False):
        self.set_calls.append((heater, temp, wait)); heater.set_temp(temp)
    def cmd_TEMPERATURE_WAIT(self, gcmd): pass

class FakePrinter:
    def __init__(self):
        self.gcode = FakeGcode(); self.heaters = FakeHeaters(); self.objects = {}; self.handlers = {}
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
    def register_event_handler(self, event, callback):
        self.handlers.setdefault(event, []).append(callback)
    def send_event(self, event):
        for callback in self.handlers.get(event, []): callback(0.0)
    def command_error(self, message): return RuntimeError(message)

class FakeConfig:
    def __init__(self, printer, values=None): self.printer = printer; self.values = values or {}
    def get_printer(self): return self.printer
    def get_name(self): return 'temperature_sensor chamber'
    def getfloat(self, key, default=None, **kwargs): return float(self.values.get(key, default))
    def error(self, message): return RuntimeError(message)

class FakeGcmd:
    def __init__(self, **params): self.params = params
    def get_float(self, name, default=None): return float(self.params.get(name, default))

class FakeSensor:
    def __init__(self):
        self.temp_lock = threading.Lock(); self.air_temp = 24.5; self.heater_temp = 25.5
        self.target_temp = 0.0; self.heater_state = False; self.fan_state = False; self.fan_duty = 0
        self.system_locked = False; self.flook_ip = '192.168.1.230'; self.ws_connected = True
        self.native_heater_enabled = True; self.native_heater_name = 'chamber'
        self.native_heater_max_temp = 65.0; self.native_heater_wait_delta = 2.0
        self.native_heater_temperature_sensor = True
        self.native_heater_temperature_sensor_name = 'chamber_heater'
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

    def test_orca_m141_and_m191_use_native_heater(self):
        printer, sensor, heater = make_heater()
        self.assertNotIn('M141', printer.gcode.commands)
        self.assertNotIn('M191', printer.gcode.commands)
        printer.send_event('klippy:ready')
        self.assertIn('M141', printer.gcode.commands)
        self.assertIn('M191', printer.gcode.commands)

        printer.gcode.commands['M141'](FakeGcmd(S=42))
        self.assertEqual(printer.heaters.set_calls[-1], (heater, 42.0, False))

        printer.gcode.commands['M191'](FakeGcmd(S=45))
        self.assertEqual(printer.heaters.set_calls[-1], (heater, 45.0, True))

        printer.gcode.commands['M191'](FakeGcmd(S=0))
        self.assertEqual(printer.heaters.set_calls[-1], (heater, 0.0, False))

    def test_orca_commands_do_not_replace_existing_handlers(self):
        printer = FakePrinter()
        sensor = FakeSensor()
        flook32.FLOOK32RemoteHeater(FakeConfig(printer), sensor, 'chamber')
        # Simulate a macro loaded later in config, but before klippy:ready.
        sentinel = object()
        printer.gcode.commands['M141'] = sentinel
        printer.send_event('klippy:ready')
        self.assertIs(printer.gcode.commands['M141'], sentinel)
        self.assertIn('M191', printer.gcode.commands)

    def test_heater_body_temperature_is_exposed_as_read_only_sensor(self):
        printer = FakePrinter(); config = FakeConfig(printer); sensor = FakeSensor()
        telemetry = flook32._register_heater_temperature_sensor(config, sensor)
        self.assertIs(printer.objects['temperature_sensor chamber_heater'], telemetry)
        self.assertEqual(
            printer.heaters.available_sensors,
            ['temperature_sensor chamber_heater'])
        self.assertEqual(telemetry.get_temp(0), (25.5, 0.0))
        self.assertEqual(telemetry.get_status(0), {'temperature': 25.5})
        self.assertTrue(any(
            x[:3] == ('TEMPERATURE_WAIT', 'SENSOR',
                      'temperature_sensor chamber_heater')
            for x in printer.gcode.mux))

    def test_heater_body_temperature_sensor_can_be_disabled(self):
        printer = FakePrinter(); config = FakeConfig(printer); sensor = FakeSensor()
        sensor.native_heater_temperature_sensor = False
        self.assertIsNone(flook32._register_heater_temperature_sensor(config, sensor))
        self.assertEqual(printer.heaters.available_sensors, [])

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

    def test_native_heater_is_reordered_after_bed_on_ready(self):
        printer = FakePrinter(); config = FakeConfig(printer); sensor = FakeSensor()
        printer.heaters.available_heaters[:] = ['extruder', 'heater_bed']
        flook32._register_remote_heater(config, sensor)
        self.assertEqual(
            printer.heaters.available_heaters,
            ['extruder', 'heater_bed', 'heater_generic chamber'])
        # Simulate later config sections being loaded after FLOOK32.
        printer.heaters.available_heaters[:] = [
            'heater_generic chamber', 'extruder', 'heater_bed']
        printer.send_event('klippy:ready')
        self.assertEqual(
            printer.heaters.available_heaters,
            ['extruder', 'heater_bed', 'heater_generic chamber'])

    def test_native_heater_falls_back_to_end_without_bed(self):
        printer = FakePrinter(); config = FakeConfig(printer); sensor = FakeSensor()
        flook32._register_remote_heater(config, sensor)
        printer.heaters.available_heaters[:] = ['heater_generic chamber', 'extruder']
        printer.send_event('klippy:ready')
        self.assertEqual(
            printer.heaters.available_heaters,
            ['extruder', 'heater_generic chamber'])

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
