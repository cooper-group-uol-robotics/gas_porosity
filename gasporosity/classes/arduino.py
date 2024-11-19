from serial import Serial
from .threads import StoppableThread
from datetime import datetime, timedelta


class readThread(StoppableThread):
    def __init__(self, arduino, lock, output, output_file_name):
        super().__init__()
        self.arduino = arduino
        self.lock = lock
        self.output = output
        self.output_file_name = output_file_name
        self.last_second = datetime.now()
        self.smoothing_list = []

    def run(self):
        while not self.stopped():
            # get pressure from arduino
            data = self.arduino.read(self.lock)
            if data:
                try:
                    splitdata = data.split(",")
                    self.arduino.pressure = splitdata[0]
                    self.arduino.dosingStatus = splitdata[1]
                    y1 = float(self.arduino.pressure)
                    # plot time against pressure
                    now = datetime.now()
                    if now - self.last_second > timedelta(seconds=1):
                        self.last_second = now
                        smooth = sum(self.smoothing_list)
                        smooth = smooth/len(self.smoothing_list)
                        self.output.push([now], [[smooth]])
                        self.smoothing_list = []
                    else:
                        self.smoothing_list.append(y1)
                    # save values to file
                    with open(self.output_file_name, "a") as file:
                        file.write(f"{now}, {y1} \n")
                except Exception as e:
                    print(f"partial message, {e}")
                    print(data)


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
