from .classes.camera import FlirCamera
from .classes.arduino import Arduino
import numpy as np
import cv2
import base64
import math
import threading
from .classes.julabo import Circulator
import time
from .classes.threads import DoseThread, readThread
import datetime

class DataController:
    def __init__(self) -> None:
        self.state = 0
        self.video_capture = None
        self.coords = []
        self.corners = []
        self.mask = []
        self.radius = 0
        self.arduino = Arduino()
        self.lock = threading.Lock()
        self.circulator = Circulator()
        self.cancel = False
        self.degas_done = False
        self.dosing_cycles = 7
        self.cycle = 0
        self.well_count_x = 12
        self.well_count_y = 8
        self.video_writer_name = datetime.datetime.today().strftime("%d%m%y_%H%M")
        self.video_writer = cv2.VideoWriter(f"data/{self.video_writer_name}.avi",-1,20,(640,480))
        self.dose_thread = None
        self.save_video = True
        
    def set_save_video(self,set):
        if set =="On":
            self.save_video = True
        else:
            self.save_video = False
        
    def set_well_count(self,x=None,y=None):
        if x is None:
            self.well_count_y = y
        elif y is None:
            self.well_count_x = x

    def read_cycle(self):
        return self.dose_thread.cycle

    def set_state(self, state):
        self.state = state
    
    def probe(self, x, y):
        return self.data[y, x]
    
   
    # ----------------- Arduino -----------------

    def dose(self,cycles):
        self.dose_thread = DoseThread(self.arduino,cycles)
        self.dose_thread.start()

    def stop_dose(self):
        self._stop_thread(self.dose_thread)

    def stop_reading(self):
        self._stop_thread(self.read_thread)
        self.arduino.close()

    def start_reading_arduino(self, output, output_file_name):
        self.arduino.open()
        self.read_thread = readThread(self.arduino, self.lock, output, output_file_name)
        self.read_thread.start()

    def _stop_thread(self, thread):
        thread.stop()
        thread.join()

    # ----------------- Degas -----------------
    def _wait(self, timetowait):
        """
        waits 5x time to wait and checks if need to cancel
        """
        for _ in range(timetowait):
            time.sleep(5)
            if self.cancel:
                self.cancel = False
                self.circulator.off()
                self.circulator.close()
                raise "canceled"

    def degas(self,heat,cool,stab,heat_wait,cool_wait,stab_wait):
        self.circulator.open()
        self.circulator.set_temp(heat)
        self.circulator.on()
        try:
            #TODO: custom wait times/temps
            self._wait(heat_wait)
            self.circulator.set_temp(cool)
            self._wait(cool_wait)
            self.circulator.set_temp(stab)
            self._wait(stab_wait)
            self.circulator.off()
            self.circulator.close()
            self.degas_done = True
        except Exception as e:
            raise e

    def cancel_degas(self):
        self.cancel = True

    # ----------------- Wells --------------
    def set_well_count(self,x=None,y=None):
        if x is None:
            self.well_count_y = y
        elif y is None:
            self.well_count_x = x

    def edit_corners(self, x, y):
        self.corners.append((x, y))

        if len(self.corners) == 5:
            # if we already have 4 corners, find the closest one
            # and replace it with the click
            min_distance = 100000
            for i, corner in enumerate(self.corners[:-1]):
                distance = abs(corner[0] - x) + abs(corner[1] - y)
                if min_distance > distance:
                    min_distance = distance
                    swap = i
            self.corners.pop(swap)

        if len(self.corners) == 4:

            topleft = []
            topright = []
            bottomleft = []
            bottomright = []

            # work out which corner is which
            sums = []

            for point in self.corners:
                sums.append(point[0] + point[1])
            # Sum of X and Y, largest is bottom right, smallest is top left (for a rectangle-like object)
            minimum_index = sums.index(min(sums))
            maximum_index = sums.index(max(sums))

            topleft = self.corners[minimum_index]
            bottomright = self.corners[maximum_index]

            if maximum_index > minimum_index:
                self.corners.pop(maximum_index)
                self.corners.pop(minimum_index)
            else:
                self.corners.pop(minimum_index)
                self.corners.pop(maximum_index)

            # of the 2 left, smallest x is bottom left
            # smallest y is top right

            if self.corners[0][0] > self.corners[1][0]:
                topright = self.corners[0]
                bottomleft = self.corners[1]
            else:
                topright = self.corners[1]
                bottomleft = self.corners[0]

            self.corners.append(topleft)
            self.corners.append(bottomright)

            self.coords = []

            # for a polygon ABCD
            # A-------B
            # |       |
            # |       |
            # |       |
            # C-------D

            # in order to draw the grid accurately with angles
            # calculate the vector AB, AC and CD
            # and cacluate the magnitude of those vectors
            # then the distance between 2 wells along those vectors
            # by dividing by the total number of wells (distances)

            # CD
            vectA = ((bottomright[0] - bottomleft[0]), (bottomright[1] - bottomleft[1]))
            magA = math.sqrt(vectA[0] * vectA[0] + vectA[1] * vectA[1])
            unit_vectA = (vectA[0] / magA, vectA[1] / magA)
            A_well_dist = magA / (self.well_count_x -1)

            # AB
            vectC = ((topright[0] - topleft[0]), (topright[1] - topleft[1]))
            magC = math.sqrt(vectC[0] * vectC[0] + vectC[1] * vectC[1])
            unit_vectC = (vectC[0] / magC, vectC[1] / magC)
            C_well_dist = magC / (self.well_count_x -1)

            # AC
            vectB = ((bottomleft[0] - topleft[0]), (bottomleft[1] - topleft[1]))
            magB = math.sqrt(vectB[0] * vectB[0] + vectB[1] * vectB[1])
            unit_vectB = (vectB[0] / magB, vectB[1] / magB)
            B_well_dist = magB / (self.well_count_y -1)

            # for each well in the well plate find a center point
            for x in range(self.well_count_x):
                row = []
                for y in range(self.well_count_y):
                    # point = top left point + components of AB and CD depending on how far down AC we are
                    pointx = (
                        topleft[0]
                        + (y / (self.well_count_y -1)) * (x * A_well_dist * unit_vectA[0])
                        + y * B_well_dist * unit_vectB[0]
                        + (1 - y / (self.well_count_y -1)) * (x * C_well_dist * unit_vectC[0])
                    )
                    pointy = (
                        topleft[1]
                        + (y / (self.well_count_y -1)) * (x * A_well_dist * unit_vectA[1])
                        + y * B_well_dist * unit_vectB[1]
                        + (1 - y / (self.well_count_y -1)) * (x * C_well_dist * unit_vectC[1])
                    )
                    row.append([pointx, pointy])
                self.coords.append(row)
            # save our coords of center point
            self.coords = np.array(self.coords)

    def edit_wells(self, x, y):
        # find the closest well and move its center to the new x,y
        min_distance = 10000000
        for i, column in enumerate(self.coords):
            for j, row in enumerate(column):
                distance = abs(row[0] - x) + abs(row[1] - y)
                if min_distance > distance:
                    min_distance = distance
                    swap = (i, j)

        self.coords[swap[0]][swap[1]] = [x, y]


    
    # ---------------- Camera ---------------------
    def start_camera(self):
        self.video_capture = FlirCamera()

    def focus(self):
        self.video_capture.auto_focus()

    def _convert(self, frame: np.ndarray) -> str:
        _, imencode_image = cv2.imencode(".jpg", frame)
        return base64.b64encode(imencode_image.tobytes()).decode("ASCII")

    def save_image(self, filename):
        frame = cv2.normalize(self.data, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
        frame = cv2.applyColorMap(frame, cv2.COLORMAP_PLASMA)
        cv2.imwrite("data/" + filename + ".png",frame)

    def get_frame(self):
        # the UI.interactive image class is expecting javascript like information
        # base64 images, so we capture our data and convert it to that
        black_1px = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAAXNSR0IArs4c6QAAAA1JREFUGFdjYGBg+A8AAQQBAHAgZQsAAAAASUVORK5CYII="
        placeholder = "data:image/jpg;base64," + black_1px

        if self.video_capture is None:
            return placeholder
        self.data = self.video_capture.capture_data()
        frame = cv2.normalize(self.data, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
        frame = cv2.applyColorMap(frame, cv2.COLORMAP_PLASMA)
        if self.save_video and self.dose_thread is not None and self.dose_thread.is_alive():
            print("save_frame")
            if self.cycle != self.dose_thread.cycle:
                self.cycle = self.dose_thread.cycle
                self.video_writer = cv2.VideoWriter(f"data/{self.video_writer_name}_cycle_{self.cycle}.avi",-1,20,(640,480))
            self.video_writer.write(frame)
        if frame is None:
            return placeholder
        # `convert` is a CPU-intensive function, so we run it in a separate process to avoid blocking the event loop and GIL.
        return "data:image/jpg;base64," + self._convert(frame)

    
    # ------------------ Data Handling -----------------
    def calculate_mask(self):
        # for each center point
        self.mask = []
        print("calculating")
        for _ in self.coords:
            for value in _:
                center_x = value[1]
                center_y = value[0]

                relevantCoords = []
                # for each pixel check if its inside the radius of the current center point, if so save it to that masks entry
                for x in range(480):
                    for y in range(640):
                        if (x - center_x) * (x - center_x) + (y - center_y) * (
                            y - center_y
                        ) < self.radius * self.radius:
                            relevantCoords.append((x, y))
                self.mask.append(relevantCoords)
        return True

    def write(self, path, timestamp):
        csvline = str(timestamp) + ","
        # for each pixel in the mask average the values for each well
        for well in self.mask:
            sum = 0
            for pixel in well:
                sum += self.data[pixel[0]][pixel[1]]
            avg = sum / len(well)
            csvline += str(avg) + ","
        csvline = csvline[:-1] + "\n"
        with open(path, "a") as file:
            file.write(csvline)

    def create_file(self, file_name):
        numbers_to_letters = {
            0: "A",
            1: "B",
            2: "C",
            3: "D",
            4: "E",
            5: "F",
            6: "G",
            7: "H",
        }
        with open(file_name, "w") as file:
            csv_line = "Timestamp,"
            for i in range(self.well_count_x):
                for j in range(self.well_count_y):
                    csv_line = csv_line + f"{i + 1}{numbers_to_letters[j]},"
            file.write(csv_line + "\n")

    def cleanup(self):
        self._stop_thread(self.read_thread)
        self._stop_thread(self.dose_thread)
        self.dose_thread.join()
        self.read_thread.join()
        self.arduino.close()
        if self.video_capture is not None:
            self.video_capture.cleanup()


if __name__ == "__main__":
    controller = DataController()
    controller.degas()
