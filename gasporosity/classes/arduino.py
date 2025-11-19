from serial import Serial



class Arduino:
    def __init__(self) -> None:
        self.ser = Serial(None, timeout=0.5)
        self.ser.port = "COM6"
        self.pressure = 0
        self.dosingStatus = 0

    def open(self):
        self.ser.open()

    def write(self, byte: bytes):
        self.ser.write(byte)

    def read(self, lock):
        # need to lock as this needs to be thread safe
        # with lock:
        try:
            return self.ser.readline().decode().strip()
        except Exception as e:
            print(e)

    def close(self):
        self.ser.close()
