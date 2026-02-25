from nicegui import ui, app, core, Client, events
from gasporosity.data_controller import DataController
import signal
from datetime import datetime
import threading
import time
import os

from scripts.calculate_porus_Yulin_ui_v2 import calculate_porus
from scripts.local_file_picker import local_file_picker

class State:
    """
    State class to change on_click properties of the image
    """

    def __init__(self, stateDict) -> None:
        self.state = 0
        self.stateDict = stateDict

    def set_state(self, state):
        self.state = state

    def state_f(self):
        return self.stateDict[self.state]

class Gas_Porosity_Ui:
    def __init__(self):
        app.on_shutdown(self.cleanup)
        signal.signal(signal.SIGINT, self.handle_sigint)

        self.controller = DataController()
        self.state = State(
            {0: self.controller.probe, 1: self.controller.edit_corners, 2: self.controller.edit_wells}
        )
        ############################# ACTUAL UI STUFF #####################################

        self.dosing_done_waiting = False
        with ui.splitter() as splitter:
            with splitter.before:
                with ui.splitter(horizontal=True) as h_splitter:
                    with h_splitter.before:
                        ui.label("Arduino Controls").style("font-family: Arial; font-size: 18px; font-weight: bold;")
                        with ui.row():
                            self.btn_start_arduino = ui.button(
                                "start Listening",
                                on_click=lambda: self.arduino_on(self.pres_file_name.text),
                            )
                            self.btn_dose = ui.button("dose", on_click=lambda: self.dose())
                            self.btn_dose.disable()
                            self.btn_stop_arduino = ui.button(
                                "stop listening", on_click=lambda: self.arduino_off()
                            )
                            ui.label("Dosing Cycles: ").style("font-family: Arial; font-size: 14px;")
                            self.number_of_cycles = ui.select(
                                [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], value=7
                            )
                            self.btn_dose_stop = ui.button(
                                "stop cycling", on_click=lambda: self.dose_stop()
                            )
                            ui.label("Current Cycle: ").style("font-family: Arial; font-size: 14px;")
                            self.text_cycle = ui.label()
                            self.btn_stop_arduino.disable()
                            self.line_plot = ui.line_plot(
                                n=1, limit=5000, figsize=(10, 3), update_every=1
                            ).with_legend(["pressure"], loc="upper center", ncol=1)
                            self.cycle_updater = ui.timer(
                                interval=5, callback=lambda: self.update_cycle(), active=False
                            )

                    with h_splitter.after:
                        with ui.splitter() as v_splitter:
                            with v_splitter.before:
                                with ui.splitter() as v_splitter_2:
                                    with v_splitter_2.before:
                                        ui.label("Circulator Controls").style("font-family: Arial; font-size: 18px; font-weight: bold;")

                                        self.btn_degas = ui.button(
                                            "Degas",
                                            on_click=lambda: self.degas(
                                                self.degas_heat_temp_input.value,
                                                self.degas_cool_temp_input.value,
                                                self.degas_stabalise_temp_input.value,
                                                self.degas_heat_time_input.value,
                                                self.degas_cool_time_input.value,
                                                self.degas_stabalise_time_input.value
                                            ),
                                        )
                                        ui.label("Degas Timer:").style("font-family: Arial; font-size: 14px;")
                                        self.timer = ui.label()
                                        self.degas_timer = ui.timer(
                                            1,
                                            callback=lambda: self.degas_timer_function(
                                                datetime.now()
                                            ),
                                            active=False,
                                        )
                                        self.btn_cancel = ui.button(
                                            "Cancel", on_click=lambda: self.degas_cancel()
                                        )
                                    with v_splitter_2.after:
                                        self.degas_heat_temp_input = ui.number(
                                            label="Degas Heat Temp",
                                            value=100,
                                        )

                                        self.degas_cool_temp_input = ui.number(
                                            label="Degas cool Temp",
                                            value=-10,
                                        )
                                        self.degas_stabalise_temp_input = ui.number(
                                            label="Degas stabilise Temp",
                                            value=20,
                                        )
                            with v_splitter.after:
                                with ui.splitter() as v_splitter2:
                                    with v_splitter2.before:
                                        self.degas_heat_time_input = ui.number(
                                            label="Degas Heat time (minutes)",
                                            value=480,
                                        )
                                        self.degas_cool_time_input = ui.number(
                                            label="Degas cool time (minutes)",
                                            value=60,
                                        )
                                        self.degas_stabalise_time_input = ui.number(
                                            label="Degas stabilise time (minutes)",
                                            value=60,
                                        )
                                    with v_splitter2.after:
                                        ui.label("File Config").style("font-family: Arial; font-size: 18px; font-weight: bold;")
                                        self.temp_file_name_input = ui.input(
                                            label="Temp File Name", value="Temperature"
                                        )
                                        self.temp_file_name = ui.label().bind_text_from(
                                            self.temp_file_name_input,
                                            "value",
                                            backward=lambda x: "data/" + x + ".csv",
                                        )
                                        self.pres_file_name_input = ui.input(
                                            label="Pressure File Name", value="Pressure"
                                        )
                                        self.temp_file_name.set_visibility(False)
                                        self.pres_file_name = ui.label().bind_text_from(
                                            self.pres_file_name_input,
                                            "value",
                                            backward=lambda x: "data/" + x + ".csv",
                                        )
                                        self.pres_file_name.set_visibility(False)
                    ui.splitter(horizontal=True).classes('w-full h-24')
                    ui.label("Data Analysis (beta)").style("font-family: Arial; font-size: 18px; font-weight: bold;")
                    ui.label("This will produce a temperature graph for you to observe the outcomes and export the peak areas and peak hights to CSVs").style("font-family: Arial; font-size: 12px;")
                    ui.label("Only works with standard dosing procedure and uses calculate_porus_yulin_ui_v2.py for processing").style("font-family: Arial; font-size: 12px;")
                    with ui.row():
                        self.threshold = ui.number(
                        label="Temperatue Threshold for peak",
                        value=0.1,
                    )
                        self.normalize_well_input = ui.input(
                            label="Normalize Well", value="1A"
                        )
                        self.normalize_well_text = ui.label().bind_text_from(
                            self.normalize_well_input,
                            "value",
                            backward=lambda x: "data/" + x + ".csv",
                        )
                        self.normalize_well_text.set_visibility(False)
                        self.file_to_run_text = ui.label().style("font-family: Arial; font-size: 8px;")
                        self.file_to_run_input = ui.button(
                            "Chose File", on_click=self.pick_file
                        )
                        
                        
                        self.btn_run_script = ui.button("Run analysis", on_click=lambda: self.run_analysis(self.file_to_run_text.text,self.threshold.value,self.normalize_well_input.value))
            with splitter.after:
                ui.label("Camera Controls").style("font-family: Arial; font-size: 18px; font-weight: bold;")
                with ui.row():
                    self.btn_start_camera = ui.button(
                        "Start Camera", on_click=lambda: self.start_camera()
                    )
                    self.btn_corners = ui.button("Edit Corners", on_click=lambda: self.state.set_state(1))
                    self.btn_corners.disable()
                    self.btn_wells = ui.button("Edit Wells", on_click=lambda: self.state.set_state(2))
                    self.btn_wells.disable()
                    self.btn_probe = ui.button("Probe", on_click=lambda: self.state.set_state(0))
                    self.btn_probe.disable()
                    self.btn_focus = ui.button("focus", on_click=lambda: self.controller.focus())
                    self.btn_focus.disable()
                    with ui.dialog() as dialog, ui.card():
                        self.file_input = ui.input("File Name:", value="CameraCapture")
                        ui.button("Save", on_click=lambda: self.save_image(self.file_input.value))
                    self.btn_save = ui.button("Save Image", on_click=lambda: dialog.open())
                    self.btn_save.disable()
                with ui.row():
                    self.btn_start_data = ui.button(
                        "Start data Capture", on_click=lambda: self.start_data_capture()
                    )
                    self.btn_start_data.disable()
                    self.btn_stop_data = ui.button(
                        "Stop data Capture", on_click=lambda: self.stop_data_capture()
                    )
                    self.btn_stop_data.disable()
                    ui.label("Save video:")
                    self.video_save_toggle = ui.toggle(["On","Off"],value="Off",on_change=lambda: self.controller.set_save_video(self.video_save_toggle.value))
                    self.video_save_toggle.disable()
                    print(self.video_save_toggle.value)

                with ui.row().classes("w-full border p-4"):
                    ui.label("Well Size").style("font-family: Arial; font-size: 14px;")
                    self.slider = (
                        ui.slider(min=0, max=20, step=0.1, value=10)
                        .props("label-always")
                        .on("update:model-value", throttle=1.0)
                    )
                self.video_image = ui.interactive_image(cross="green", on_mouse=self.mouse_handler)
                with ui.row().classes("w-full border p-4"):
                    ui.label("Number of X Wells").style("font-family: Arial; font-size: 14px;")
                    self.slider_x_wells = (
                        ui.slider(
                            min=4,
                            max=12,
                            step=1,
                            value=12,
                            on_change=lambda: self.controller.set_well_count(x=self.slider_x_wells.value),
                        )
                        .props("label-always")
                        .on("update:model-value", throttle=1.0)
                    )
                    ui.label("Number of Y Wells").style("font-family: Arial; font-size: 14px;")
                    self.slider_y_wells = (
                        ui.slider(
                            min=4,
                            max=8,
                            step=1,
                            value=8,
                            on_change=lambda: self.controller.set_well_count(y=self.slider_y_wells.value),
                        )
                        .props("label-always")
                        .on("update:model-value", throttle=1.0)
                    )
                ui.timer(interval=0.1, callback=lambda: self.update_image())
                self.writer = ui.timer(
                    interval=1,
                    callback=lambda: self.controller.write(
                        self.temp_file_name.text, datetime.now().time()
                    ),
                    active=False,
                )
                self.auto_stop_timer = ui.timer(
                    interval=500, callback=lambda: self.check_done(), active=False
                )
############################ BUTTON LOGIC ################################

    def start_data_capture(self):
        """
        calculates mask then starts the data capture
        """
        self.btn_start_data.disable()
        self.controller.radius = self.slider.value
        self.mask_thread = threading.Thread(target=self.calculate_mask, daemon=True)
        self.mask_thread.start()
        ui.notify("calculating mask please wait")


    def calculate_mask(self):

        self.controller.calculate_mask()
        self.controller.create_file(self.temp_file_name.text)
        self.btn_stop_data.enable()
        self.writer.activate()


    def stop_data_capture(self):
        self.btn_start_data.enable()
        self.btn_stop_data.disable()
        self.writer.deactivate()


    def start_camera(self):
        """
        enables and disables ui elements then starts the camera
        """
        try:
            self.controller.start_camera()
            self.btn_start_camera.disable()
            self.btn_corners.enable()
            self.btn_wells.enable()
            self.btn_probe.enable()
            self.btn_focus.enable()
            self.btn_save.enable()
        except Exception as e:
            ui.notify(e)


    def mouse_handler(self,e: events.MouseEventArguments):
        """
        Depending on the state of the system,
        get the mouse_on_click function and feed the X,Y coords of the image
        """

        function = self.state.state_f()
        x = e.image_x
        y = e.image_y
        ret = function(x, y)
        if len(self.controller.coords) > 0:
            self.btn_start_data.enable()
            self.video_save_toggle.enable()
        if ret is not None:
            ui.notify(ret)
        return ret

        
    def arduino_on(self,file_name):
        try:
            self.controller.start_reading_arduino(self.line_plot, file_name)
            self.btn_start_arduino.disable()
            self.btn_stop_arduino.enable()
            self.btn_dose.enable()
        except Exception as e:
            ui.notify(e)


    def arduino_off(self):
        try:
            self.controller.stop_reading()
            self.btn_start_arduino.enable()
            self.btn_stop_arduino.disable()
            self.btn_dose.disable()
        except Exception as e:
            ui.notify(e)


    def degas(self,heat, cool, stab,heat_time,cool_time,stab_time):
        # minutes * 60 for seconds / 5 for _wait function 
        heat_time = int(heat_time * 12)
        cool_time = int(cool_time * 12)
        stab_time = int(stab_time * 12)
        thread = threading.Thread(
            target=self.controller.degas, args=[heat,cool,stab,heat_time,cool_time,stab_time]
        )
        thread.start()
        time.sleep(1)
        if thread.is_alive():
            self.degas_start_time = datetime.now()
            self.degas_timer.activate()
        else:
            ui.notify("Degas Failed, see console for more info")


    def degas_cancel(self):
        self.degas_start_time = None
        self.timer.set_text("Cancelled")
        self.degas_timer.deactivate()
        self.controller.cancel_degas()


    def degas_timer_function(self,timenow):

        timeDiff = timenow - self.degas_start_time
        self.timer.set_text(str(timeDiff))
        if self.controller.degas_done:
            self.timer.set_text("Degas Done, Time Taken: " + str(timeDiff))
            self.degas_timer.deactivate()
            self.controller.degas_done = False
            self.degas_start_time = None


    def dose(self):
        self.controller.dose(self.number_of_cycles.value)
        self.cycle_updater.activate()
        self.auto_stop_timer.activate()


    def dose_stop(self):
        self.controller.stop_dose()
        self.text_cycle.set_text("")
        self.cycle_updater.deactivate()


    def update_cycle(self):
        cycle = self.controller.read_cycle()
        self.text_cycle.set_text(cycle)


    def save_image(self,filename):
        self.controller.save_image(filename)
        ui.notify("Saved")
        self.dialog.close()


    def check_done(self):
        if not self.controller.dose_thread.is_alive():

            if not self.dosing_done_waiting:
                self.dosing_done_waiting = True
                return
            self.text_cycle.set_text("Dosing Complete")
            self.stop_data_capture()
            self.arduino_off()
            self.auto_stop_timer.deactivate()

    async def pick_file(self):
        result = await local_file_picker(os.getcwd(),multiple=False)
        self.file_to_run_text.text = result[0]
        
    def run_analysis(self,file_to_run,threshold,normalize_well):
        calculate_porus(file_to_run,threshold,normalize_well)
        ui.notify(f"Files for analysis created at: {os.getcwd()}")
        
    ################### IMAGE UPDATING ######################
    def update_image(self):
        """
        get the frames and updates the video image
        """
        self.video_image.set_source(self.controller.get_frame())
        self.draw_circles()





    def draw_circles(self):
        """
        draws the circles on the video image
        """
        self.video_image.content = ""
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
        for i, x in enumerate(self.controller.coords):
            for j, y in enumerate(x):
                color = "SkyBlue"
                self.video_image.content += f'<circle cx="{y[0]}" cy="{y[1]}" r="{self.slider.value}" fill="none" stroke="{color}" stroke-width="3" />'
                self.video_image.content += f'<text x={y[0] + self.slider.value} y={y[1] + self.slider.value} stroke="white" font-size="10">{i + 1}{numbers_to_letters[j]}</text>'
        for corner in self.controller.corners:
            color = "Green"
            self.video_image.content += f'<circle cx="{corner[0]}" cy="{corner[1]}" r="{self.slider.value}" fill="none" stroke="{color}" stroke-width="3" />'


    ############################# WEBSITE HANDLING THINGS ###############################
    async def disconnect(self) -> None:
        """Disconnect all clients from current running server."""
        for client_id in Client.instances:
            await core.sio.disconnect(client_id)


    async def cleanup(self) -> None:
        # This prevents ugly stack traces when auto-reloading on code change,
        # because otherwise disconnected clients try to reconnect to the newly started server.
        await self.disconnect()
        # Release the webcam hardware so it can be used by other applications again.
        self.controller.cleanup()


    def handle_sigint(self,signum, frame) -> None:
        # `disconnect` is async, so it must be called from the event loop; we use `ui.timer` to do so.
        ui.timer(0.1, self.disconnect, once=True)
        # Delay the default handler to allow the disconnect to complete.
        ui.timer(1, lambda: signal.default_int_handler(signum, frame), once=True)


@ui.page('/')
def main():
    my_ui = Gas_Porosity_Ui()


ui.run()
