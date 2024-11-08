from serial import Serial

class Pheonix:
    def __init__(self) -> None:
        self.ser = Serial(None, timeout=0.5)
        self.ser.port = "COM5"

    def on(self):
        self.write(b"GO\r")
        print(self.read())
    
    def off(self):
        self.write(b"ST\r")
        print(self.read())

    def set_temp(self,temp):
        bytes_to_write = f"S  {temp}\r" 
        self.write(bytes_to_write.encode())
        print(self.read())
    
    def get_temp(self):
        self.write(b"I\r")
        temp = self.read()
        return temp

    def open(self):
        self.ser.open()

    def write(self, byte: bytes):
        self.ser.write(byte)

    def read(self):
        # need to lock as this needs to be thread safe
        #with lock:
        try:

            return self.ser.readline().decode().strip()
        except Exception as e:
            print(e)

    def reads(self):
        while True:
            print(self.read())
    def close(self):
        self.ser.close()

if __name__ == "__main__":
    pheonix = Pheonix()
    pheonix.open()
    #thread = threading.Thread(target=pheonix.reads)
    #thread.start()
    pheonix.set_temp("08000")
    print(pheonix.read())
    pheonix.write(b"S\r")
    print(pheonix.read())
    input()
    pheonix.write(b"S  -1000\r")
    print(pheonix.read())
    pheonix.write(b"S\r")
    print(pheonix.read())
    input()
    pheonix.write(b"S  02000\r")
    print(pheonix.read())
    pheonix.write(b"S\r")
    print(pheonix.read())
    input()
    pheonix.close()
    