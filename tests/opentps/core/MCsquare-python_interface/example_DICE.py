import os
from scipy.spatial import distance

from Process.PatientData import *

# user config:
patient_data_path = "data/"

# Load patient data
Patients = PatientList() # initialize list of patient data
Patients.list_dicom_files(patient_data_path, 1) # search dicom files in the patient data folder
#Patients.print_patient_list() # list files
Patients.list[0].import_patient_data() # import patient 0
Patients.list[0].RTstructs[0].print_ROINames()

# find first contour
patient_id, struct_id, contour_id = Patients.find_contour('PTV')
X = Patients.list[patient_id].RTstructs[struct_id].Contours[contour_id] # PTV contour

# find second contour
patient_id, struct_id, contour_id = Patients.find_contour('Prostate')
Y = Patients.list[patient_id].RTstructs[struct_id].Contours[contour_id] # Prostate contour

# Compute DICE = 2 * |X ∩ Y| / (|X| + |Y|)
DICE = 1.0 - distance.dice(X.Mask.flatten(), Y.Mask.flatten())
print("DICE (" + X.ROIName + ", " + Y.ROIName + ") = " + str(DICE))
