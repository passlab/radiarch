import os
from matplotlib import pyplot as plt

from Process.PatientData import *
from Process.SPRimage import *

# User config:
patient_data_path = "./data"
Scanner = "default" # folder in MCsquare/Scanners
GantryAngle = 180
CouchAngle = 0

# Load patient data
Patients = PatientList()
Patients.list_dicom_files(patient_data_path, 1)
Patients.list[0].import_patient_data() # import patient 0

# compute WET distribution inside ROI
CT = Patients.list[0].CTimages[0]
SPR = SPRimage()
SPR.convert_CT_to_SPR(CT, Scanner)

# compute WET over the entire image
WET = SPR.compute_WET_map(GantryAngle, CouchAngle) # without ROI

# compute WET inside ROI only
#Patients.list[0].RTstructs[0].print_ROINames()
#ROI = Patients.list[0].RTstructs[0].Contours[7] # PTV 74 gy
#WET = SPR.compute_WET_map(GantryAngle, CouchAngle, ROI) 


# display results
print("Minimum WET: ", WET.min(), " mm")
print("Maximum WET: ", WET.max(), " mm")

plt.subplot(1,2,1)
plt.imshow(SPR.Image[:,:,35], cmap='gray')
plt.title("SPR")
plt.subplot(1,2,2)
plt.imshow(WET[:,:,35], cmap='gray')
plt.title("WET")
plt.show()
