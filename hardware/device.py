"""GPIO adapters for the provided active-low relay and digital sensors."""
import threading
import time

class Device:
    def __init__(self):
        import RPi.GPIO as GPIO
        self.gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        self.soil_pin, self.rain_pin, self.relay_pin = 17, 27, 22
        GPIO.setup(self.soil_pin, GPIO.IN)
        GPIO.setup(self.rain_pin, GPIO.IN)
        GPIO.setup(self.relay_pin, GPIO.OUT, initial=GPIO.HIGH)
        self.lock = threading.Lock()
        self.timer = None

    def read_sensors(self):
        # Many comparator modules are active-low; adjust these two booleans if yours differ.
        return {'soil_dry': self.gpio.input(self.soil_pin) == self.gpio.LOW,
                'rain_detected': self.gpio.input(self.rain_pin) == self.gpio.LOW,
                'pump_on': self.gpio.input(self.relay_pin) == self.gpio.LOW,
                'timestamp': time.time(), 'simulated': False}

    def pump_off(self):
        with self.lock:
            if self.timer: self.timer.cancel(); self.timer = None
            self.gpio.output(self.relay_pin, self.gpio.HIGH)

    def pump_for(self, seconds):
        self.pump_off()
        with self.lock:
            self.gpio.output(self.relay_pin, self.gpio.LOW)
            self.timer = threading.Timer(seconds, self.pump_off)
            self.timer.daemon = True
            self.timer.start()

    def move(self, direction):
        raise RuntimeError('Motor pins and ENA/ENB wiring are not specified; motor control is disabled safely.')

    def close(self):
        self.pump_off()
        self.gpio.cleanup()
