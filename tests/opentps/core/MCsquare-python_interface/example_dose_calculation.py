import os
from matplotlib import pyplot as plt

from Process.PatientData import *
from Process.MCsquare import *
from Process.RTdose import *
from Process.DVH import *

# user config:
patient_data_path = "data/"
Num_Simulated_paticles = 1e7    # simulate minimum 1E7 particles
Max_Stat_uncertainty = 2.0      # reach at maximum 2% MC noise
OutputDirectory = "output/"
OutputPlan = os.path.join(OutputDirectory, "Plan_copy.dcm")
OutputDose = os.path.join(OutputDirectory, "MCsquare_dose.dcm")

# create output folder
if not os.path.isdir(OutputDirectory):
  os.mkdir(OutputDirectory)
  

# Load patient data
Patients = PatientList() # initialize list of patient data
Patients.list_dicom_files(patient_data_path, 1) # search dicom files in the patient data folder
Patients.print_patient_list() # list files
Patients.list[0].import_patient_data() # import patient 0
Patients.list[0].RTstructs[0].print_ROINames()

# prepare data
CT = Patients.list[0].CTimages[0]
Plan = Patients.list[0].Plans[0]
TPS_dose = Patients.list[0].RTdoses[0]

# find Target contour
patient_id, struct_id, contour_id = Patients.find_contour('PTV')
Target = Patients.list[patient_id].RTstructs[struct_id].Contours[contour_id] # PTV contour

# find OAR contour
patient_id, struct_id, contour_id = Patients.find_contour('Rectum')
OAR = Patients.list[patient_id].RTstructs[struct_id].Contours[contour_id] # Rectum contour

# Configure MCsquare
mc2 = MCsquare()
mc2.BDL.selected_BDL = "default" # Beam model (this refers to MCsquare/BDL/default.txt)
mc2.Scanner.selected_Scanner = "default" # CT scanner calibration (this refers to MCsquare/Scanners/default)
mc2.NumProtons = Num_Simulated_paticles
mc2.MaxUncertainty = Max_Stat_uncertainty
mc2.dose2water = True

# crop the CT image provided to MCsquare using the External contour (not used in sample data)
#patient_id, struct_id, contour_id = Patients.find_contour('External')
#External = Patients.list[patient_id].RTstructs[struct_id].Contours[contour_id]
#mc2.Crop_CT_contour = External

# run MCsquare simulation
mc2.MCsquare_version() # display the version of MCsquare
mhd_dose = mc2.MCsquare_simulation(CT, Plan)

# Add new dose to patient data
MC2_dose = RTdose().Initialize_from_MHD(mc2.DoseName, mhd_dose, CT, Plan)
Patients.list[0].RTdoses.append(patient_data_path + "")

# Export dose to dicom format
plan_uid = Plan.export_Dicom_with_new_UID(OutputPlan)
MC2_dose.export_Dicom(OutputDose, plan_uid)

# Resample computed dose to the original TPS dose grid
#Resampled_dose = MC2_dose.copy()
#Resampled_dose.resample_image(TPS_dose.OriginalGridSize, TPS_dose.OriginalImagePositionPatient, TPS_dose.OriginalPixelSpacing)
#Resampled_dose.export_Dicom(os.path.join(OutputDirectory, "Resampled_dose.dcm"), plan_uid)

# Compute DVH
TPS_DVH_target = DVH(TPS_dose, Target)
MC2_DVH_target = DVH(MC2_dose, Target)
TPS_DVH_OAR = DVH(TPS_dose, OAR)
MC2_DVH_OAR = DVH(MC2_dose, OAR)

print("\nDVH metrics:\n")
print("Target D95  = " + str(MC2_DVH_target.D95) + " Gy")
print("Target D5   = " + str(MC2_DVH_target.D5) + " Gy")
print("OAR Dmean   = " + str(MC2_DVH_OAR.Dmean) + " Gy")

# Find target center
maskY,maskX,maskZ = np.nonzero(Target.Mask)
target_center = [np.mean(maskX), np.mean(maskY), np.mean(maskZ)]
Z_coord = int(target_center[2])

# Display result
plt.figure(figsize=(10,4))
plt.subplot(1, 2, 1)
plt.imshow(CT.Image[:,:,Z_coord], cmap='gray')
plt.imshow(Target.ContourMask[:,:,Z_coord], alpha=.2, cmap='binary')
dose_threshold = np.percentile(MC2_dose.Image, 99.99) # reduce impact of MC noise in the displayed dose colormap
plt.imshow(MC2_dose.Image[:,:,Z_coord], alpha=.2, cmap='jet', vmin=0, vmax=dose_threshold)
plt.title("Dose distribution")

plt.subplot(1, 2, 2)
plt.plot(TPS_DVH_target.dose, TPS_DVH_target.volume, label=TPS_DVH_target.ROIName+" (TPS)")
plt.plot(MC2_DVH_target.dose, MC2_DVH_target.volume, label=MC2_DVH_target.ROIName+" (MCsquare)")
plt.plot(TPS_DVH_OAR.dose, TPS_DVH_OAR.volume, label=TPS_DVH_OAR.ROIName+" (TPS)")
plt.plot(MC2_DVH_OAR.dose, MC2_DVH_OAR.volume, label=MC2_DVH_OAR.ROIName+" (MCsquare)")
plt.ylim(0, 100)
plt.ylim(0, 100)
plt.legend()
plt.title("DVH")
plt.xlabel("Dose (Gy)")
plt.ylabel("Volume (%)")

plt.show()


