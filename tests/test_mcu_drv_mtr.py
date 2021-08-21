import struct
import time

from unittest import TestCase

from serial import Serial, SerialTimeoutException
from serial.tools.list_ports import comports

from adapters.mcu_drv_mtr import MCUDrvMtr
from domain.interfaces import InputData
from domain.request_model import RequestObject
from domain.use_cases import Measure

class MCUDrvMtrTest(TestCase):
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
					if len(init_data) != 2:
						continue
					
					init_val = struct.unpack("<h", init_data)[0]
					if init_val >= 1024:
						# initial data should be ADC result so the maximum value is 1023
						continue
					
					return port.serial_number
			except SerialTimeoutException:
				continue
		
		self.skipTest("Couldn't find Arduino with DrvMtr sketch.")
	
	def test_create(self):
		dut = MCUDrvMtr("", 0)
	
	def test_measure(self):
		baudrate = 500000
		sn = self.get_device(baudrate)
		data_count = 10*256
		with MCUDrvMtr(sn, data_count, return_format="<h", init_size=2, baudrate=baudrate) as dut:
			uc = Measure(dut, dut)
			res = uc(RequestObject(
				driver_data = InputData([0]),
				retry = 2,
				measure_timeout = 10,
			))
			
			self.assertEqual(data_count, len(res))
