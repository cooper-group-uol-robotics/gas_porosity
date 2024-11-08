import PySpin
import numpy as np


class FlirCamera:
    def __init__(self):
        self.system: PySpin.System = PySpin.System.GetInstance()

        cam_list = self.system.GetCameras()

        if cam_list.GetSize() != 1:
            cam_list.Clear()

            # Release system instance
            self.system.ReleaseInstance()

            raise Exception("None OR Multple cameras are connected")

        self.cam = cam_list[0]

        self.cam.Init()
        sNodemap = self.cam.GetTLStreamNodeMap()
        self.nodemap = self.cam.GetNodeMap()
        node_bufferhandling_mode = PySpin.CEnumerationPtr(
            sNodemap.GetNode("StreamBufferHandlingMode")
        )
        if not PySpin.IsReadable(node_bufferhandling_mode) or not PySpin.IsWritable(
            node_bufferhandling_mode
        ):
            raise Exception("Unable to set stream buffer handling mode.. Aborting...")

        node_newestonly = node_bufferhandling_mode.GetEntryByName("NewestOnly")
        if not PySpin.IsReadable(node_newestonly):
            raise Exception("Unable to set stream buffer handling mode.. Aborting...")

        # Retrieve integer value from entry node
        node_newestonly_mode = node_newestonly.GetValue()

        # Set integer value from entry node as new value of enumeration node
        node_bufferhandling_mode.SetIntValue(node_newestonly_mode)
        node_acquisition_mode = PySpin.CEnumerationPtr(
            self.cam.GetNodeMap().GetNode("AcquisitionMode")
        )
        if not PySpin.IsReadable(node_acquisition_mode) or not PySpin.IsWritable(
            node_acquisition_mode
        ):
            print(
                "Unable to set acquisition mode to continuous (enum retrieval). Aborting..."
            )
            return False

        # Retrieve entry node from enumeration node
        node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName(
            "Continuous"
        )
        if not PySpin.IsReadable(node_acquisition_mode_continuous):
            print(
                "Unable to set acquisition mode to continuous (entry retrieval). Aborting..."
            )
            return False

        # Retrieve integer value from entry node
        acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()

        # Set integer value from entry node as new value of enumeration node
        node_acquisition_mode.SetIntValue(acquisition_mode_continuous)
        print("Acquisition mode set to continuous...")
        # technically (probably) shouldnt do this but it creates less lag for the camera
        self.cam.BeginAcquisition()

    def cleanup(self):
        # need to end/release camera properly on shutdown
        self.cam.EndAcquisition()
        self.cam.DeInit()
        del self.cam
        self.system.ReleaseInstance()

    def capture_data(self):
        # get the image
        image_result = self.cam.GetNextImage(1000)
        if image_result.IsIncomplete():
            print(
                "Image incomplete with image status %d ..."
                % image_result.GetImageStatus()
            )
        else:
            # convert to array
            image_data: np.ndarray = image_result.GetNDArray()
            # convert to degrees C
            image_data = image_data * 0.1
            subract = np.ones(image_data.shape) * 273.15
            self.image_data = np.subtract(image_data, subract)
            image_result.Release()
        return self.image_data

    def auto_focus(self):
        """
        run the auto focus cmd on the camera 
        """
        autoFocus = PySpin.CCommandPtr(self.nodemap.GetNode("AutoFocus"))
        autoFocus.Execute()

    def set_emissivity(self, emissivity: float):
        """
        set emissivity to value (expected value between 0 and 1)
        """
        PySpin.CFloatPtr(self.nodemap.GetNode("ObjectEmissivity")).SetValue(emissivity)

    def set_distance(self, distance):
        """
        set the distance to the value (expected value between 0 and 1)
        """
        PySpin.CFloatPtr(self.nodemap.GetNode("ObjectDistance")).SetValue(distance)


if __name__ == "__main__":
    camera = FlirCamera()
    print(camera.capture_frame())
    print("haha")
