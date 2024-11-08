from gasporosity.classes.camera import FlirCamera
import sys

def change_distance(distance):
    camera = FlirCamera()
    camera.set_emissivity(distance)
    camera.cleanup()


if __name__ == "__main__":
    change_distance(float(sys.argv[1]))