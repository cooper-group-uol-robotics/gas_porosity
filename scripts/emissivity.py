from gasporosity.classes.camera import FlirCamera
import sys

def change_emissivity(emissivity):
    camera = FlirCamera()
    camera.set_emissivity(emissivity)
    camera.cleanup()


if __name__ == "__main__":
    change_emissivity(float(sys.argv[1]))