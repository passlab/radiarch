import os
from pathlib import Path
from typing import List, Sequence, Optional, Tuple, Union
import numpy as np

import nibabel as nib
import pydicom
import logging

from opentps.core.data._patientData import PatientData
from opentps.core.data._patient import Patient
from opentps.core.data._patientList import PatientList
from opentps.core.data.images._image3D import Image3D  
from opentps.core.data.images._mrImage import MRImage
from opentps.core.data.images._ctImage import CTImage
from opentps.core.data.images._roiMask import ROIMask
from opentps.core.io.dicomIO import readDicomCT, readDicomMRI, readDicomDose, readDicomVectorField, readDicomStruct, readDicomPlan, readDicomRigidTransform, readDicomPET
from opentps.core.io import mhdIO
from opentps.core.io.serializedObjectIO import loadDataStructure
from opentps.core.processing.imageProcessing.sitkImageProcessing import REGSITK

logger = logging.getLogger(__name__)

def loadData(patientList:PatientList, dataPath:str, maxDepth=-1, ignoreExistingData:bool=True, importInPatient:Optional[Patient]=None):
    """
    Load all data found at the given input path.

    Parameters
    ----------
    patientList: PatientList
        The patient list to which the data will be added.

    dataPath: str or list
        Path or list of paths pointing to the data to be loaded.

    maxDepth: int, optional
        Maximum subfolder depth where the function will check for data to be loaded.
        Default is -1, which implies recursive search over infinite subfolder depth.

    ignoreExistingData: bool, optional
        If True, the function will not load data that is already present in the patient list.
        Default is True. (not implemented yet)

    importInPatient: Patient, optional
        If given, the data will be imported into the given patient.
        Default is None, which implies that the data will be imported into a new patient.

    Returns
    -------
    dataList: list of data objects
        The function returns a list of data objects containing the imported data.
    """
    #TODO: implement ignoreExistingData
    
    dataList = readData(dataPath, maxDepth=maxDepth)

    patient = None

    if not (importInPatient is None):
        dataList = dataList[0].patientData
        patient = importInPatient

    for data in dataList:
        if (isinstance(data, Patient)):
            newPatient = data
            try:
                newPatient = patientList.getPatientByPatientId(patient.id)
            except:
                patientList.append(newPatient)

            if importInPatient is None:
                patient = newPatient

        elif importInPatient is None:
            # check if patient already exists
            try:
                patient = patientList.getPatientByPatientId(data.patient.id)
            except:
                pass

            # TODO: Get patient by name?

        if patient is None:
            if data.patient is None:
                data.patient = Patient(name='New patient')

            patient = data.patient

            patientList.append(patient)

        if patient is None:
            patient = Patient()
            patientList.append(patient)

        # add data to patient
        if(isinstance(data, PatientData)):
            patient.appendPatientData(data)
        elif (isinstance(data, Patient)):
            pass  # see above, the Patient case is considered
        else:
            logging.warning("WARNING: " + str(data.__class__) + " not loadable yet")
            continue

def readData(inputPaths, maxDepth=-1, do_reg=True) -> Sequence[Union[PatientData, Patient]]:
    """
    Load all data found at the given input path.

    Parameters
    ----------
    inputPaths: str or list
        Path or list of paths pointing to the data to be loaded.

    maxDepth: int, optional
        Maximum subfolder depth where the function will check for data to be loaded.
        Default is -1, which implies recursive search over infinite subfolder depth.

    Returns
    -------
    dataList: list of data objects
        The function returns a list of data objects containing the imported data.

    """

    fileLists = listAllFiles(inputPaths, maxDepth=maxDepth)
    dataList = []

    # read Dicom files
    dicomCT = {}
    dicomMRI = {}
    dicomPET = {}

    for d, filePath in enumerate(fileLists["Dicom"]):
        logger.info(f'Loading data {d+1}/{len(fileLists["Dicom"])} Dicom files : {os.path.basename(filePath)}.')
        dcm = pydicom.dcmread(filePath)

        # Dicom field
        if dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.66.3" or (hasattr(dcm, 'Modality') and dcm.Modality == "REG"):
            if hasattr(dcm,'RegistrationSequence'):
                transform = readDicomRigidTransform(filePath)
                dataList += transform # not append because readDicomRigidTransform returns a list already
            if hasattr(dcm,'DeformableRegistrationSequence'):
                field = readDicomVectorField(filePath)
                dataList.append(field)

        # Dicom CT
        elif dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.2":
            # Dicom CT are not loaded directly. All slices must first be classified according to SeriesInstanceUID.

            # this checks if a breathingPeriod file is present in the ct folder or in the parent of the ct folder
            # if yes, this ct slice is given a dynamic series index
            dynSeriesIndex = -1
            for txtFilePathIndex, txtFilePath in enumerate(fileLists["txt"]):
                if txtFilePath.endswith('breathingPeriod.txt'):
                    if os.path.dirname(txtFilePath) == os.path.dirname(filePath) or os.path.dirname(txtFilePath) == os.path.dirname(os.path.dirname(filePath)):
                        dynSeriesIndex = txtFilePathIndex
                        ## associer la slice à une série 4D

            newCT = 1
            for key in dicomCT:
                if key == dcm.SeriesInstanceUID:
                    dicomCT[dcm.SeriesInstanceUID].append(filePath)
                    newCT = 0
            if newCT == 1:
                dicomCT[dcm.SeriesInstanceUID] = [dynSeriesIndex, filePath]
        
        # Dicom MRI
        elif dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.4":
            # Dicom MRI are not loaded directly. All slices must first be classified according to SeriesInstanceUID.
            newMRI = 1
            dynSeriesIndex = -1
            for key in dicomMRI:
                #print(key)
                if key == dcm.SeriesInstanceUID:
                    dicomMRI[dcm.SeriesInstanceUID].append(filePath)
                    newMRI = 0

            if newMRI == 1:
                dicomMRI[dcm.SeriesInstanceUID] = [dynSeriesIndex, filePath]
       
        # Dicom PET
        # Positron Emission Tomography Image Storage: 1.2.840.10008.5.1.4.1.1.128
        # Enhanced PET Image Storage (if present): 1.2.840.10008.5.1.4.1.1.130
        elif dcm.SOPClassUID in ("1.2.840.10008.5.1.4.1.1.128", "1.2.840.10008.5.1.4.1.1.130"):
            # collect PET slices by SeriesInstanceUID (same pattern as CT/MR)
            newPET = 1
            dynSeriesIndex = -1
            for key in dicomPET:
                if key == dcm.SeriesInstanceUID:
                    dicomPET[dcm.SeriesInstanceUID].append(filePath)
                    newPET = 0
            if newPET == 1:
                dicomPET[dcm.SeriesInstanceUID] = [dynSeriesIndex, filePath]

        # Dicom dose
        elif dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.481.2":
            dose = readDicomDose(filePath)
            dataList.append(dose)

        # Dicom RT Photon and Ion plan
        elif dcm.SOPClassUID in ("1.2.840.10008.5.1.4.1.1.481.8","1.2.840.10008.5.1.4.1.1.481.5"):
            plan = readDicomPlan(filePath)
            dataList.append(plan)

        # Dicom struct
        elif dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.481.3":
            struct = readDicomStruct(filePath)
            dataList.append(struct)

        else:
            logging.warning("WARNING: Unknown SOPClassUID " + dcm.SOPClassUID + " for file " + filePath)
     
    # import Dicom CT images
    for key in dicomCT:
        logger.debug('in dataLoader readData, for key in dicomCT {}'.format(key))
        logger.debug(dicomCT[key][0])
        ct = readDicomCT(dicomCT[key][1:])
        dataList.append(ct)

    # import Dicom MR images
    for key in dicomMRI:
        logger.debug('in dataLoader readData, for key in dicomMRI {}'.format(key))
        logger.debug(dicomMRI[key][0])
        mri = readDicomMRI(dicomMRI[key][1:])
        dataList.append(mri)

    # import Dicom PET images
    for key in dicomPET:
        logger.debug('in dataLoader readData, for key in dicomPET {}'.format(key))
        logger.debug(dicomPET[key][0])
        pet = readDicomPET(dicomPET[key][1:])
        dataList.append(pet)

    # read MHD images
    for d, filePath in enumerate(fileLists["MHD"]):
        logger.info(f'Loading data {d}/{len(fileLists["MHD"])} MHD files : {os.path.basename(filePath)}.')
        mhdImage = mhdIO.importImageMHD(filePath)
        dataList.append(mhdImage)

    # read serialized object files
    for d, filePath in enumerate(fileLists["Serialized"]):
        logger.info(f'Loading data {d}/{len(fileLists["Serialized"])} Serialized files : {os.path.basename(filePath)}.')
        dataList += loadDataStructure(filePath) # not append because loadDataStructure returns a list already
        print('---------', type(dataList[-1]))


    #If REG file is present, associate the transform to the corresponding CT and MR series
    #it is assumed the reg is from MR to CT, and that the static image is the CT and the moving image is the MR, but this can be adapted in the future if needed
    if do_reg:
        for i,data in enumerate(dataList): 
            if data.name == "Transform":
                staticId = None
                movingId = None
                movingId_sec = []
                movingIndex_sec = []
                for j, otherdata in enumerate(dataList):
                    
                    if otherdata.seriesInstanceUID == data.staticImageSeriesID:
                        staticId = otherdata.seriesInstanceUID

                    if otherdata.seriesInstanceUID == data.movingImageSeriesID:
                        movingId = otherdata.seriesInstanceUID
                        movingIndex = j
                    #also transform if images in same FOR as the moving image in the REG file, even if not explicitly referenced as moving image in the REG file
                    elif otherdata.name != "Transform":
                        if otherdata.frameOfReferenceUID == data.FORUID:
                            movingId_sec.append(otherdata.seriesInstanceUID)
                            movingIndex_sec.append(j)

                if (staticId is  None) or (movingId is  None): 
                    print("WARNING: could not find static or moving image for registration, skipping registration for this transform")
                else: 
                    #get folder paths of the static and moving images, which will be used for the registration
                    staticpath = str(Path(dicomCT[staticId][1]).parent)
                    movingpath = str(Path(dicomMRI[movingId][1]).parent)
                    moving = REGSITK(staticpath, movingpath,data.tformMatrix, movingId)
                    dataList[movingIndex] = moving
                        
                    # also transform secondary moving images
                    for k, sec_moving in enumerate(movingId_sec):
                        movingpath = str(Path(dicomMRI[sec_moving][1]).parent)
                        moving = REGSITK(staticpath, movingpath,data.tformMatrix, sec_moving)
                        dataList[movingIndex_sec[k]] = moving
                        
    return dataList

 
def readSingleData(filePath, pathdict = {}, target=None):
    """
    Load a single data object from the given input path.

    Parameters
    ----------
    filePath: str
        Path pointing to the data to be loaded. Can be a file or directory path.

    pathdict: dict, optional
        Dictionary to store series organized by SeriesInstanceUID. 
        Used internally to group CT or MR slices belonging to the same series.
        Default is {}.

    type: str, optional
        Type of image to load. Supported values are "CT" or "MR".
        Default is "CT".
    
    target: str, optional
        If given, the function will look for a series with SeriesInstanceUID matching the target value
        and load that series. If not given, the function will load the first series found in the directory.
        Default is None.

    Returns
    -------
    PatientData
        The loaded data object (CT, MR, dose, plan, struct, field, or serialized data).
        Returns None if the file type cannot be recognized.

    """
    if os.path.isdir(filePath):
        # Check that it is a DICOM  otherwise error
        listFiles = listAllFiles(filePath, maxDepth=0)
        if len(listFiles['Serialized'])>0 or len(listFiles['MHD'])>0:
            logging.error('readSingleData should not contain multiple files')
            return
        for file_i in listFiles["Dicom"]:
            readSingleData(file_i, pathdict=pathdict, target=target)
        if len(pathdict)==0:
            logging.error('readSingleData should not contain multiple files')
            return
        #import Dicom CT images
        if len(pathdict)>1:
            
            logging.error('readSingleData should not contain multiple series. First one is taken as default')
        if target in pathdict:
            File = pathdict[target] 
            print("target {} found in pathdict, loading this series".format(target))
        else:
            File = list(pathdict.values())[0]

        #File = list(pathdict.values())[0]
        
        # Auto-detect image type from the first file's SOPClassUID
        first_file = File[0] if isinstance(File, list) else File
        dcm = pydicom.dcmread(first_file)
   
        detected_type = "CT" if dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.2" else "MR" if dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.4" else None
        if detected_type is None:
            logging.error('Could not auto-detect image type from SOPClassUID. Please specify the type explicitly.')
            return
        
        if detected_type == "CT":
            print("in readSingleData, reading CT")
            img = readDicomCT(File)
        elif detected_type == "MR":
            print("in readSingleData, reading MR")
            img = readDicomMRI(File)
        return img
    else:
        filetype = get_file_type(filePath)
        if filetype == 'Dicom':
            dcm = pydicom.dcmread(filePath)

            # Dicom field
            if dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.66.3" or (hasattr(dcm, 'Modality') and dcm.Modality == "REG"):
                field = readDicomVectorField(filePath)
                return field

            # Dicom CT
            elif dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.2":
                # Dicom CT are not loaded directly. All slices must first be classified according to SeriesInstanceUID.
                newCT = 1
                for key in pathdict:
                    if key == dcm.SeriesInstanceUID:
                        pathdict[dcm.SeriesInstanceUID].append(filePath)
                        newCT = 0
                if newCT == 1:
                    pathdict[dcm.SeriesInstanceUID] = [filePath]

            # Dicom MRI
            elif dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.4":  
                 # Dicom MRI are not loaded directly. All slices must first be classified according to SeriesInstanceUID.
                
                newMRI = 1
                for key in pathdict:
                    if key == dcm.SeriesInstanceUID:
                        pathdict[dcm.SeriesInstanceUID].append(filePath)
                        newMRI = 0

                if newMRI == 1:
                    pathdict[dcm.SeriesInstanceUID] = [filePath]
                
            # Dicom dose
            elif dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.481.2":
                dose = readDicomDose(filePath)
                return dose

            # Dicom RT plan
            elif dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.481.5":
                logging.warning("WARNING: cannot import ", filePath, " because photon RT plan is not implemented yet")

            # Dicom RT Ion plan
            elif dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.481.8":
                plan = readDicomPlan(filePath)
                return plan

            # Dicom struct
            elif dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.481.3":
                struct = readDicomStruct(filePath)
                return struct

            else:
                logging.warning("WARNING: Unknown SOPClassUID " + dcm.SOPClassUID + " for file " + filePath)

        # read MHD image
        if filetype == "MHD":
            mhdImage = mhdIO.importImageMHD(filePath)
            return mhdImage

        # read serialized object files
        if filetype == "Serialized":
            return loadDataStructure(filePath)
        
        if filetype is None:
            return None


def get_file_type(filePath):
    # Is Dicom file ?
    dcm = None
    try:
        dcm = pydicom.dcmread(filePath)
    except:
        pass
    if(dcm != None):
        return 'Dicom'

    # Is MHD file ?
    with open(filePath, 'rb') as fid:
        data = fid.read(50*1024)  # read 50 kB, which should be more than enough for MHD header
        if data.isascii():
            if("ElementDataFile" in data.decode('ascii')): # recognize key from MHD header
                return 'MHD'

    # Is serialized file ?
    if filePath.endswith('.p') or filePath.endswith('.pbz2') or filePath.endswith('.pkl') or filePath.endswith('.pickle'):
        return "Serialized"

    # Is txt file ?
    if filePath.endswith('.txt'):
        return 'txt'

    logging.info("INFO: cannot recognize file format of " + filePath)
    return None



def listAllFiles(inputPaths, maxDepth=-1):
    """
    List all files of compatible data format from given input paths.

    Parameters
    ----------
    inputPaths: str or list
        Path or list of paths pointing to the data to be listed.

    maxDepth: int, optional
        Maximum subfolder depth where the function will check for files to be listed.
        Default is -1, which implies recursive search over infinite subfolder depth.

    Returns
    -------
    fileLists: dictionary
        The function returns a dictionary containing lists of data files classified according to their file format (Dicom, MHD).

    """

    fileLists = {
        "Dicom": [],
        "MHD": [],
        "Serialized": [],
        "txt": []
    }
    # if inputPaths is a list of path, then iteratively call this function with each path of the list
    if(isinstance(inputPaths, list)):
        for path in inputPaths:
            lists = listAllFiles(path, maxDepth=maxDepth)
            for key in fileLists:
                fileLists[key] += lists[key]

        return fileLists


    # check content of the input path
    if os.path.isdir(inputPaths):
        inputPathContent = sorted(os.listdir(inputPaths))
    else:
        inputPathContent = [inputPaths]
        inputPaths = ""


    for fileName in inputPathContent:
        filePath = os.path.join(inputPaths, fileName)

        # folders
        if os.path.isdir(filePath):
            if(maxDepth != 0):
                subfolderFileList = listAllFiles(filePath, maxDepth=maxDepth-1)
                for key in fileLists:
                    fileLists[key] += subfolderFileList[key]

        # files
        elif os.path.isfile(filePath):
            filetype = get_file_type(filePath)
            if filetype is None:
                logging.info("INFO: cannot recognize file format of " + filePath)
            else:
                fileLists[filetype].append(filePath)

    return fileLists


def readNifti(filePath, type="Image3D"):
    """
    Load a NIfTI image from the given input path.

    Parameters
    ----------
    filePath: str
        Path pointing to the NIfTI file to be loaded (binary mask).

    type: str, optional
        Type of image to load. Supported values are "Image3D", "CT", "MR", and "mask".
        Default is "Image3D".

    Returns
    -------
    Image3D or CTImage or MRImage or ROIMask
        The loaded NIfTI image converted to the corresponding OpenTPS image object.

    """

    img = nib.load(filePath)
    imgheader = img.header
    
    # Extract data and convert from RAS (NIfTI) back to LPS (Dicom)
    data = img.get_fdata()[::-1, ::-1, :]
    
    # Extract origin and convert from RAS to LPS
    origin_ras = img.affine[0:3, 3]
    origin_lps = [-origin_ras[0], -origin_ras[1], origin_ras[2]]
    
    spacing = imgheader.get_zooms()

    if type == "Image3D":
        image = Image3D(data, origin = origin_lps, spacing = spacing)
    if type == "CT":
        image = CTImage(data, origin = origin_lps, spacing = spacing)
    if type == "MR":
        image = MRImage(data, origin = origin_lps, spacing = spacing)
    if type == "mask":
        image = ROIMask(data, origin = origin_lps, spacing = spacing)

    name = os.path.basename(filePath)
    if name.endswith('.nii.gz'):
        name = name[:-7]
    elif name.endswith('.nii'):
        name = name[:-4]
    image.name = name
    return image

def writeNifti(image:Image3D, filePath):
    """
    Save a single data object to the given output path.

    Parameters
    ----------
    image: Image3D
        Image3D object to be saved as NIfTI.

    filePath: str
        Path pointing to the output directory where the NIfTI file will be written.

    Returns
    -------
    None
        The function saves the image on disk and does not return a value.

    """
    #Save image as nifti file
    #NIFTI assumes RAS normally, while DICOM and SITK is LPS 
    #flip image and struct to convert from LPS to RAS (nifti standard)
    data = image.imageArray[::-1, ::-1, :]
    
    sx, sy, sz = image.spacing
    ox, oy, oz = image.origin

    # Affine matrix: spacing on the diagonal and the LPS-to-RAS inverted origin in the last column
    affine = np.diag([sx, sy, sz, 1.0])
    affine[0:3, 3] = [-ox, -oy, oz]

    image_nii = nib.Nifti1Image(data, affine=affine)
    nib.save(image_nii, os.path.join(filePath, image.name + '.nii.gz'))
    print("Saved image {} at {}".format(image.name, os.path.join(filePath, image.name + '.nii.gz')))
    
def set_header_info(nii_file: nib.Nifti1Image, 
                    voxelsize: Tuple[float], 
                    image_position_patient: List[float]):
    """
    Sets the header information of a Nifti file and returns it
    Parameters:
        - nii_file: Nifti file to which we want to add header information
        - voxelsize: List of floats corresponding to voxel size in x, y and z direction
        - image_position_patient: Origin of image
    """
    nii_file.header['pixdim'][1] = voxelsize[0]
    nii_file.header['pixdim'][2] = voxelsize[1]
    nii_file.header['pixdim'][3] = voxelsize[2]
    
    #affine - voxelsize
    nii_file.affine[0][0] = voxelsize[0]
    nii_file.affine[1][1] = voxelsize[1]
    nii_file.affine[2][2] = voxelsize[2]
    #affine - imagecorner
    nii_file.affine[0][3] = image_position_patient[0]
    nii_file.affine[1][3] = image_position_patient[1]
    nii_file.affine[2][3] = image_position_patient[2]
    return nii_file