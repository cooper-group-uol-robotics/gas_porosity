from nicegui import ui, app, core, Client, events
from gasporosity.data_controller import DataController
import signal
from datetime import datetime
import threading


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


############################ BUTTON LOGIC ################################
def start_data_capture():
    """
    calculates mask then starts the data capture
    """
    global btn_start_data
    btn_start_data.disable()
    controller.radius = slider.value
    mask_thread = threading.Thread(target=calculate_mask, daemon=True)
    mask_thread.start()
    ui.notify("calculating mask please wait")


def calculate_mask():
    global btn_stop_data
    controller.calculate_mask()
    global temp_file_name
    controller.create_file(temp_file_name.text)
    btn_stop_data.enable()
    writer.activate()


def stop_data_capture():
    btn_start_data.enable()
    btn_stop_data.disable()
    writer.deactivate()


def start_camera():
    """
    enables and disables ui elements then starts the camera
    """
    try:
        controller.start_camera()
        btn_start_camera.disable()
        btn_corners.enable()
        btn_wells.enable()
        btn_probe.enable()
        btn_focus.enable()
    except Exception as e:
        ui.notify(e)


def mouse_handler(e: events.MouseEventArguments):
    """
    Depending on the state of the system,
     get the mouse_on_click function and feed the X,Y coords of the image
    """

    function = state.state_f()
    x = e.image_x
    y = e.image_y
    ret = function(x, y)
    if len(controller.coords) > 0:
        btn_start_data.enable()
    if ret is not None:
        ui.notify(ret)
    return ret


def arduino_on(file_name):
    try:
        controller.start_reading_arduino(line_plot, file_name)
        btn_start_arduino.disable()
        btn_stop_arduino.enable()
        btn_dose.enable()
    except Exception as e:
        ui.notify(e)


def arduino_off():
    try:
        controller.stop_reading()
        btn_start_arduino.enable()
        btn_stop_arduino.disable()
        btn_dose.disable()
    except Exception as e:
        ui.notify(e)


def degas():
    thread = threading.Thread(target=controller.degas)
    thread.start()
    global degas_start_time
    degas_start_time = datetime.now()
    degas_timer.activate()


def degas_cancel():
    global degas_start_time
    degas_start_time = None
    timer.set_text("Cancelled")
    degas_timer.deactivate()
    controller.cancel_degas()


def degas_timer_function(timenow):
    global degas_start_time
    timeDiff = timenow - degas_start_time
    timer.set_text(str(timeDiff))
    if controller.degas_done:
        timer.set_text("Degas Done, Time Taken: " + str(timeDiff))
        degas_timer.deactivate()
        controller.degas_done = False
        degas_start_time = None


def dose():
    controller.dose()
    cycle_updater.activate()


def dose_stop():
    controller.stop_dose()
    text_cycle.set_text("")
    cycle_updater.deactivate()

def update_cycle():
    cycle = controller.read_cycle()
    text_cycle.set_text(cycle)

################### IMAGE UPDATING ######################
def update_image():
    """
    get the frames and updates the video image
    """
    video_image.set_source(controller.get_frame())
    draw_circles()


def draw_circles():
    """
    draws the circles on the video image
    """
    video_image.content = ""
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
    for i, x in enumerate(controller.coords):
        for j, y in enumerate(x):
            color = "SkyBlue"
            video_image.content += f'<circle cx="{y[0]}" cy="{y[1]}" r="{slider.value}" fill="none" stroke="{color}" stroke-width="3" />'
            video_image.content += f'<text x={y[0] + slider.value} y={y[1] + slider.value} stroke="white" font-size="10">{i + 1}{numbers_to_letters[j]}</text>'
    for corner in controller.corners:
        color = "Green"
        video_image.content += f'<circle cx="{corner[0]}" cy="{corner[1]}" r="{slider.value}" fill="none" stroke="{color}" stroke-width="3" />'


############################# WEBSITE HANDLING THINGS ###############################
async def disconnect() -> None:
    """Disconnect all clients from current running server."""
    for client_id in Client.instances:
        await core.sio.disconnect(client_id)


async def cleanup() -> None:
    # This prevents ugly stack traces when auto-reloading on code change,
    # because otherwise disconnected clients try to reconnect to the newly started server.
    await disconnect()
    # Release the webcam hardware so it can be used by other applications again.
    controller.cleanup()


def handle_sigint(signum, frame) -> None:
    # `disconnect` is async, so it must be called from the event loop; we use `ui.timer` to do so.
    ui.timer(0.1, disconnect, once=True)
    # Delay the default handler to allow the disconnect to complete.
    ui.timer(1, lambda: signal.default_int_handler(signum, frame), once=True)


############################# ACTUAL UI STUFF #####################################
app.on_shutdown(cleanup)
signal.signal(signal.SIGINT, handle_sigint)

controller = DataController()
state = State(
    {0: controller.probe, 1: controller.edit_corners, 2: controller.edit_wells}
)
global btn_stop_data
with ui.splitter() as splitter:
    with splitter.before:
        with ui.splitter(horizontal=True) as h_splitter:
            with h_splitter.before:
                ui.label("Arduino Controls")
                with ui.row():
                    btn_start_arduino = ui.button(
                        "start Listening",
                        on_click=lambda: arduino_on(pres_file_name.text),
                    )
                    btn_dose = ui.button("dose", on_click=lambda: dose())
                    btn_dose.disable()
                    btn_stop_arduino = ui.button(
                        "stop listening", on_click=lambda: arduino_off()
                    )
                    ui.label("Dosing Cycles: ")
                    number_of_cycles = ui.select(
                        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], value=7
                    )
                    btn_dose_stop = ui.button(
                        "stop cycling", on_click=lambda: dose_stop()
                    )
                    text_cycle = ui.label()
                    btn_stop_arduino.disable()
                    line_plot = ui.line_plot(
                        n=1, limit=5000, figsize=(10, 5), update_every=5
                    ).with_legend(["pressure"], loc="upper center", ncol=1)
                    cycle_updater = ui.timer(interval=5, callback=lambda: update_cycle(), active=False)

            with h_splitter.after:
                with ui.splitter() as v_splitter:
                    with v_splitter.before:
                        ui.label("Pheonix Controls")
                        btn_degas = ui.button("Degas", on_click=lambda: degas())
                        ui.label("Degas Timer:")
                        timer = ui.label()
                        degas_timer = ui.timer(
                            1,
                            callback=lambda: degas_timer_function(datetime.now()),
                            active=False,
                        )
                        btn_cancel = ui.button(
                            "Cancel", on_click=lambda: degas_cancel()
                        )
                    with v_splitter.after:
                        ui.label("File Config")
                        temp_file_name_input = ui.input(
                            label="Temp File Name", value="Temperature"
                        )
                        temp_file_name = ui.label().bind_text_from(
                            temp_file_name_input,
                            "value",
                            backward=lambda x: "data/" + x + ".csv",
                        )
                        pres_file_name_input = ui.input(
                            label="Pressure File Name", value="Pressure"
                        )
                        temp_file_name.set_visibility(False)
                        pres_file_name = ui.label().bind_text_from(
                            pres_file_name_input,
                            "value",
                            backward=lambda x: "data/" + x + ".csv",
                        )
                        pres_file_name.set_visibility(False)
    with splitter.after:
        ui.label("Camera Controls")
        with ui.row():
            btn_start_camera = ui.button(
                "Start Camera", on_click=lambda: start_camera()
            )
            btn_corners = ui.button("Edit Corners", on_click=lambda: state.set_state(1))
            btn_corners.disable()
            btn_wells = ui.button("Edit Wells", on_click=lambda: state.set_state(2))
            btn_wells.disable()
            btn_probe = ui.button("Probe", on_click=lambda: state.set_state(0))
            btn_probe.disable()
            btn_start_data = ui.button(
                "Start data Capture", on_click=lambda: start_data_capture()
            )
            btn_start_data.disable()
            btn_stop_data = ui.button(
                "Stop data Capture", on_click=lambda: stop_data_capture()
            )
            btn_stop_data.disable()
            btn_focus = ui.button("focus", on_click=lambda: controller.focus())
            btn_focus.disable()
        with ui.row().classes("w-full border p-4"):
            slider = (
                ui.slider(min=0, max=20, step=0.1, value=10)
                .props("label-always")
                .on("update:model-value", throttle=1.0)
            )
        video_image = ui.interactive_image(cross="green", on_mouse=mouse_handler)
        ui.timer(interval=0.1, callback=lambda: update_image())
        writer = ui.timer(
            interval=1,
            callback=lambda: controller.write(
                temp_file_name.text, datetime.now().time()
            ),
            active=False,
        )


ui.run()
