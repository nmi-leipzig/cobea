import struct
import time

from unittest import TestCase

from serial import Serial, SerialTimeoutException
from serial.tools.list_ports import comports

from adapters.temp_meter import TempMeter
from domain.request_model import ResponseObject, RequestObject


class TempMeterTest(TestCase):
	def get_device(self, baudrate=500000):
		ports = comports()
		arduino_ports = [p for p in ports if p.manufacturer and p.manufacturer.startswith("Arduino")]
		for port in arduino_ports:
			try:
				with Serial(port=port.device, baudrate=baudrate, timeout=2, write_timeout=2) as arduino:
					arduino.reset_input_buffer()
					arduino.reset_output_buffer()
					
					# Arduino reboots on connecting serial -> wait till reboot is done
					time.sleep(2)
					
					# check if initial data is send
					time.sleep(1)
					init_data = arduino.read(2)
					if len(init_data) > 0:
						continue
					
					arduino.write(b"i")
					sn_data = arduino.read(8)
					if len(sn_data) < 8:
						continue
					sn_int = struct.unpack("<Q", sn_data)[0]
					return port.serial_number
			except SerialTimeoutException:
				continue
		
		self.skipTest("Couldn't find Arduino with TempMeter sketch.")
	
	def test_create(self):
		dut = TempMeter()

	def test_prepare(self):
		baudrate = 500000
		sn = self.get_device(baudrate)
		with TempMeter(baudrate, sn) as dut:
			res = dut.prepare(RequestObject())
			self.assertIsInstance(res, ResponseObject)

	def test_measure(self):
		baudrate = 500000
		sn = self.get_device(baudrate)
		with TempMeter(baudrate, sn) as dut:
			dut.prepare(RequestObject())
			dut.measure(RequestObject())
