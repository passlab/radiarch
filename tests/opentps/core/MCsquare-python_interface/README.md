# Python_Interface

## Overview
Python interface for MCsquare. It enables:
* conversion of Dicom files to MCsquare input format
* call MCsquare executable to run the simulation
* load MCsquare outputs in python for post-processing

## Installation
1. Download or clone the git repository on your system.
2. Install required python modules using pip:

``` 
pip3 install --upgrade --user pip
pip3 install --user pydicom
pip3 install --user numpy
pip3 install --user scipy
pip3 install --user matplotlib
pip3 install --user Pillow
pip3 install --user shutil
```

## Run example
Sample data are provided in the data folder.
Run the example_dose_calculation.py script to convert Dicom files to MCsquare format and launch the simulation:

```
python3 example_dose_calculation.py
```
