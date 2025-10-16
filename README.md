Get the spinnaker sdk from https://www.teledynevisionsolutions.com/products/spinnaker-sdk/?model=Spinnaker%20SDK&vertical=machine%20vision&segment=iis

## Installation

1. Download and install the Spinnaker SDK from the link above
2. clone this repo
```bash
git clone https://github.com/cooper-group-uol-robotics/gas_porosity.git
```
3. Install this package and its dependencies:
    ```bash
    pip install ./gas_porosity
    ```

## Usage
Navigate to the scripts folder

Run the application:
```bash
python ui.py
```

**Important:** Verify that the port configurations in each class match your hardware setup before running.

to quickly change the camera settings you can run the `distance.py` or `emissivity.py` scripts