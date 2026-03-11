import threading
import time
from datetime import datetime, timedelta

class StoppableThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

class DoseThread(StoppableThread):
    def __init__(self, arduino, cycles):
        super().__init__()
        self.cycles = cycles
        self.cycle = 0
        self.arduino = arduino

    def run(self):
        count = 0
        while not self.stopped():
            if self.cycle == 0:
                self.arduino.write(b"1")
                self.cycle +=1
                time.sleep(10)
            
            if self.arduino.dosingStatus != "1":
                if count == 300:
                    self.arduino.write(b"1")
                    count = 0
                    self.cycle += 1
                else:
                    count += 5
                    
            if self.cycle >= self.cycles:
                self.stop()
            time.sleep(5)

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
                        self.output(smooth)
                        self.smoothing_list = []
                    else:
                        self.smoothing_list.append(y1)
                    # save values to file
                    with open(self.output_file_name, "a") as file:
                        file.write(f"{now}, {y1} \n")
                except Exception as e:
                    print(f"partial message, {e}")
                    print(data)