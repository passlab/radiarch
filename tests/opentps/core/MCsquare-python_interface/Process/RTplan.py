import pydicom
import numpy as np
import math
import time
import pickle


class RTplan:

  def __init__(self):
    self.SeriesInstanceUID = ""
    self.SOPInstanceUID = ""
    self.PatientInfo = {}
    self.StudyInfo = {}
    self.DcmFile = ""
    self.Modality = ""
    self.RadiationType = ""
    self.ScanMode = ""
    self.TreatmentMachineName = ""
    self.NumberOfFractionsPlanned = 1
    self.NumberOfSpots = 0
    self.Beams = []
    self.TotalMeterset = 0.0
    self.PlanName = ""
    self.isLoaded = 0
    self.beamlets = []
    self.OriginalDicomDataset = []
    
    
    
  def print_plan_info(self, prefix=""):
    print(prefix + "Plan: " + self.SeriesInstanceUID)
    print(prefix + "   " + self.DcmFile)
    
    
  
  def import_Dicom_plan(self):
    if(self.isLoaded == 1):
      print("Warning: RTplan " + self.SeriesInstanceUID + " is already loaded")
      return
      
    dcm = pydicom.dcmread(self.DcmFile)
    
    self.OriginalDicomDataset = dcm
    
    # Photon plan
    if dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.481.5": 
      print("ERROR: Conventional radiotherapy (photon) plans are not supported")
      self.Modality = "Radiotherapy"
      return
  
    # Ion plan  
    elif dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.481.8":
      self.Modality = "Ion therapy"
    
      if dcm.IonBeamSequence[0].RadiationType == "PROTON":
        self.RadiationType = "Proton"
      else:
        print("ERROR: Radiation type " + dcm.IonBeamSequence[0].RadiationType + " not supported")
        self.RadiationType = dcm.IonBeamSequence[0].RadiationType
        return
       
      if dcm.IonBeamSequence[0].ScanMode == "MODULATED":
        self.ScanMode = "MODULATED" # PBS
      elif dcm.IonBeamSequence[0].ScanMode == "LINE":
        self.ScanMode = "LINE" # Line Scanning
      else:
        print("ERROR: Scan mode " + dcm.IonBeamSequence[0].ScanMode + " not supported")
        self.ScanMode = dcm.IonBeamSequence[0].ScanMode
        return 
    
    # Other  
    else:
      print("ERROR: Unknown SOPClassUID " + dcm.SOPClassUID + " for file " + self.DcmFile)
      self.Modality = "Unknown"
      return
      
    # Start parsing PBS plan
    self.SOPInstanceUID = dcm.SOPInstanceUID
    self.NumberOfFractionsPlanned = int(dcm.FractionGroupSequence[0].NumberOfFractionsPlanned)
    self.NumberOfSpots = 0
    self.TotalMeterset = 0  
    
    if(hasattr(dcm.IonBeamSequence[0], 'TreatmentMachineName')):
      self.TreatmentMachineName = dcm.IonBeamSequence[0].TreatmentMachineName
    else:
      self.TreatmentMachineName = ""
  
    for dcm_beam in dcm.IonBeamSequence:
      if dcm_beam.TreatmentDeliveryType != "TREATMENT":
        continue
      
      first_layer = dcm_beam.IonControlPointSequence[0]
      
      beam = Plan_IonBeam()
      beam.SeriesInstanceUID = self.SeriesInstanceUID
      beam.BeamName = dcm_beam.BeamName
      beam.IsocenterPosition = [float(first_layer.IsocenterPosition[0]), float(first_layer.IsocenterPosition[1]), float(first_layer.IsocenterPosition[2])]
      beam.GantryAngle = float(first_layer.GantryAngle)
      beam.PatientSupportAngle = float(first_layer.PatientSupportAngle)
      beam.FinalCumulativeMetersetWeight = float(dcm_beam.FinalCumulativeMetersetWeight)
    
      # find corresponding beam in FractionGroupSequence (beam order may be different from IonBeamSequence)
      ReferencedBeam_id = next((x for x, val in enumerate(dcm.FractionGroupSequence[0].ReferencedBeamSequence) if val.ReferencedBeamNumber == dcm_beam.BeamNumber), -1)
      if ReferencedBeam_id == -1:
        print("ERROR: Beam number " + dcm_beam.BeamNumber + " not found in FractionGroupSequence.")
        print("This beam is therefore discarded.")
        continue
      else: beam.BeamMeterset = float(dcm.FractionGroupSequence[0].ReferencedBeamSequence[ReferencedBeam_id].BeamMeterset)
    
      self.TotalMeterset += beam.BeamMeterset
    
      if dcm_beam.NumberOfRangeShifters == 0:
        beam.RangeShifterID = ""
        beam.RangeShifterType = "none"
      elif dcm_beam.NumberOfRangeShifters == 1:
        beam.RangeShifterID = dcm_beam.RangeShifterSequence[0].RangeShifterID
        if dcm_beam.RangeShifterSequence[0].RangeShifterType == "BINARY":
          beam.RangeShifterType = "binary"
        elif dcm_beam.RangeShifterSequence[0].RangeShifterType == "ANALOG":
          beam.RangeShifterType = "analog"
        else:
          print("ERROR: Unknown range shifter type for beam " + dcm_beam.BeamName)
          beam.RangeShifterType = "none"
      else: 
        print("ERROR: More than one range shifter defined for beam " + dcm_beam.BeamName)
        beam.RangeShifterID = ""
        beam.RangeShifterType = "none"
      
      
      SnoutPosition = 0
      if hasattr(first_layer, 'SnoutPosition'):
        SnoutPosition = float(first_layer.SnoutPosition)
    
      IsocenterToRangeShifterDistance = SnoutPosition
      RangeShifterWaterEquivalentThickness = ""
      RangeShifterSetting = "OUT"
      ReferencedRangeShifterNumber = 0
    
      if hasattr(first_layer, 'RangeShifterSettingsSequence'):
        if hasattr(first_layer.RangeShifterSettingsSequence[0], 'IsocenterToRangeShifterDistance'):
          IsocenterToRangeShifterDistance = float(first_layer.RangeShifterSettingsSequence[0].IsocenterToRangeShifterDistance)
        if hasattr(first_layer.RangeShifterSettingsSequence[0], 'RangeShifterWaterEquivalentThickness'):
          RangeShifterWaterEquivalentThickness = float(first_layer.RangeShifterSettingsSequence[0].RangeShifterWaterEquivalentThickness)
        if hasattr(first_layer.RangeShifterSettingsSequence[0], 'RangeShifterSetting'):
          RangeShifterSetting = first_layer.RangeShifterSettingsSequence[0].RangeShifterSetting
        if hasattr(first_layer.RangeShifterSettingsSequence[0], 'ReferencedRangeShifterNumber'):
          ReferencedRangeShifterNumber = int(first_layer.RangeShifterSettingsSequence[0].ReferencedRangeShifterNumber)
       
      CumulativeMeterset = 0
      
      
      for dcm_layer in dcm_beam.IonControlPointSequence:
        
        if(self.ScanMode == "MODULATED"):
          if dcm_layer.NumberOfScanSpotPositions == 1: sum_weights = dcm_layer.ScanSpotMetersetWeights
          else: sum_weights = sum(dcm_layer.ScanSpotMetersetWeights)
          
        elif(self.ScanMode == "LINE"):
          sum_weights = sum(np.frombuffer(dcm_layer[0x300b1096].value, dtype=np.float32).tolist())                   
      
        if sum_weights == 0.0:
          continue
        
        layer = Plan_IonLayer()
        layer.SeriesInstanceUID = self.SeriesInstanceUID
            
        if hasattr(dcm_layer, 'SnoutPosition'):
          SnoutPosition = float(dcm_layer.SnoutPosition)
        
        if hasattr(dcm_layer, 'NumberOfPaintings'): layer.NumberOfPaintings = int(dcm_layer.NumberOfPaintings)
        else: layer.NumberOfPaintings = 1
       
        layer.NominalBeamEnergy = float(dcm_layer.NominalBeamEnergy)
        
        if(self.ScanMode == "MODULATED"):
          layer.ScanSpotPositionMap_x = dcm_layer.ScanSpotPositionMap[0::2]
          layer.ScanSpotPositionMap_y = dcm_layer.ScanSpotPositionMap[1::2]
          layer.ScanSpotMetersetWeights = dcm_layer.ScanSpotMetersetWeights
          layer.SpotMU = np.array(dcm_layer.ScanSpotMetersetWeights) * beam.BeamMeterset / beam.FinalCumulativeMetersetWeight # spot weights are converted to MU
          if layer.SpotMU.size == 1: layer.SpotMU = [layer.SpotMU]
          else: layer.SpotMU = layer.SpotMU.tolist()
          self.NumberOfSpots += len(layer.SpotMU)
          CumulativeMeterset += sum(layer.SpotMU)
          layer.CumulativeMeterset = CumulativeMeterset
        
        elif(self.ScanMode == "LINE"): 
          #print("SpotNumber: ", dcm_layer[0x300b1092].value)
          #print("SpotValue: ", np.frombuffer(dcm_layer[0x300b1094].value, dtype=np.float32).tolist())
          #print("MUValue: ", np.frombuffer(dcm_layer[0x300b1096].value, dtype=np.float32).tolist())
          #print("SizeValue: ", np.frombuffer(dcm_layer[0x300b1098].value, dtype=np.float32).tolist())
          #print("PaintValue: ", dcm_layer[0x300b109a].value)
          LineScanPoints = np.frombuffer(dcm_layer[0x300b1094].value, dtype=np.float32).tolist()
          layer.LineScanControlPoint_x = LineScanPoints[0::2]
          layer.LineScanControlPoint_y = LineScanPoints[1::2]
          layer.LineScanControlPoint_Weights = np.frombuffer(dcm_layer[0x300b1096].value, dtype=np.float32).tolist()
          layer.LineScanControlPoint_MU = np.array(layer.LineScanControlPoint_Weights) * beam.BeamMeterset / beam.FinalCumulativeMetersetWeight # weights are converted to MU
          if layer.LineScanControlPoint_MU.size == 1: layer.LineScanControlPoint_MU = [layer.LineScanControlPoint_MU]
          else: layer.LineScanControlPoint_MU = layer.LineScanControlPoint_MU.tolist()          
        
            
        if beam.RangeShifterType != "none":        
          if hasattr(dcm_layer, 'RangeShifterSettingsSequence'):
            RangeShifterSetting = dcm_layer.RangeShifterSettingsSequence[0].RangeShifterSetting
            ReferencedRangeShifterNumber = dcm_layer.RangeShifterSettingsSequence[0].ReferencedRangeShifterNumber
            if hasattr(dcm_layer.RangeShifterSettingsSequence[0], 'IsocenterToRangeShifterDistance'):
              IsocenterToRangeShifterDistance = dcm_layer.RangeShifterSettingsSequence[0].IsocenterToRangeShifterDistance
            if hasattr(dcm_layer.RangeShifterSettingsSequence[0], 'RangeShifterWaterEquivalentThickness'):
              RangeShifterWaterEquivalentThickness = dcm_layer.RangeShifterSettingsSequence[0].RangeShifterWaterEquivalentThickness
        
          layer.RangeShifterSetting = RangeShifterSetting
          layer.IsocenterToRangeShifterDistance = IsocenterToRangeShifterDistance
          layer.RangeShifterWaterEquivalentThickness = RangeShifterWaterEquivalentThickness
          layer.ReferencedRangeShifterNumber = ReferencedRangeShifterNumber
        
        
        beam.Layers.append(layer)
      
      self.Beams.append(beam)
      
    self.isLoaded = 1



  def convert_LineScanning_to_PBS(self, SpotDensity=10): # SpotDensity: number of simulated spots per cm.
    if(self.ScanMode != "LINE"):
      print("ERROR: Scan mode " + self.ScanMode + " cannot be converted to PBS plan")
      return
    
    self.NumberOfSpots = 0
    
    for beam in self.Beams:
      beam.FinalCumulativeMetersetWeight = 0
      beam.BeamMeterset = 0
      
      for layer in beam.Layers:
        layer.ScanSpotPositionMap_x = []
        layer.ScanSpotPositionMap_y = []
        layer.ScanSpotMetersetWeights = []
        layer.SpotMU = []
        
        for i in range(len(layer.LineScanControlPoint_x)-1):
          x_start = layer.LineScanControlPoint_x[i] # mm
          x_stop = layer.LineScanControlPoint_x[i+1] # mm
          y_start = layer.LineScanControlPoint_y[i] # mm
          y_stop = layer.LineScanControlPoint_y[i+1] # mm
          distance = math.sqrt( (x_stop-x_start)**2 + (y_stop-y_start)**2 ) / 10 # cm
          NumSpots = math.ceil(distance*SpotDensity)
          SpotWeight = layer.LineScanControlPoint_Weights[i+1] / NumSpots
          SpotMU = layer.LineScanControlPoint_MU[i+1] / NumSpots
          
          layer.ScanSpotPositionMap_x.extend(np.linspace(x_start, x_stop, num=NumSpots))
          layer.ScanSpotPositionMap_y.extend(np.linspace(y_start, y_stop, num=NumSpots))
          layer.ScanSpotMetersetWeights.extend([SpotWeight]*NumSpots)
          layer.SpotMU.extend([SpotMU]*NumSpots)
          self.NumberOfSpots += NumSpots
      
        beam.BeamMeterset += sum(layer.SpotMU)
        beam.FinalCumulativeMetersetWeight += sum(layer.ScanSpotMetersetWeights)
        layer.CumulativeMeterset = beam.BeamMeterset
      
    self.ScanMode = "MODULATED"
    print("Line scanning plan converted to PBS plan with spot density of ", SpotDensity, " spots per cm.")
    


  def export_Dicom_with_new_UID(self, OutputFile):
    # generate new uid
    initial_uid = self.OriginalDicomDataset.SOPInstanceUID
    new_uid = pydicom.uid.generate_uid()
    self.OriginalDicomDataset.SOPInstanceUID = new_uid

    # save dicom file
    print("Export dicom RTPLAN: " + OutputFile)
    self.OriginalDicomDataset.save_as(OutputFile)

    # restore initial uid
    self.OriginalDicomDataset.SOPInstanceUID = initial_uid

    return new_uid



  def save(self, file_path):
    beamlets = self.beamlets
    self.beamlets = []
    dcm = self.OriginalDicomDataset
    self.OriginalDicomDataset = []

    with open(file_path, 'wb') as fid:
      pickle.dump(self.__dict__, fid)

    self.beamlets = beamlets
    self.OriginalDicomDataset = dcm



  def load(self, file_path):
    with open(file_path, 'rb') as fid:
      tmp = pickle.load(fid)

    self.__dict__.update(tmp) 
  
    
  
      
class Plan_IonBeam:

  def __init__(self):
    self.SeriesInstanceUID = ""
    self.BeamName = ""
    self.IsocenterPosition = [0,0,0]
    self.GantryAngle = 0.0
    self.PatientSupportAngle = 0.0
    self.FinalCumulativeMetersetWeight = 0.0
    self.BeamMeterset = 0.0
    self.RangeShifter = "none"
    self.Layers = []
    
    
    
class Plan_IonLayer:

  def __init__(self):
    self.SeriesInstanceUID = ""
    self.NumberOfPaintings = 1
    self.NominalBeamEnergy = 0.0
    self.ScanSpotPositionMap_x = []
    self.ScanSpotPositionMap_y = []
    self.ScanSpotMetersetWeights = []
    self.SpotMU = []
    self.CumulativeMeterset = 0.0
    self.RangeShifterSetting = 'OUT'
    self.IsocenterToRangeShifterDistance = 0.0
    self.RangeShifterWaterEquivalentThickness = 0.0
    self.ReferencedRangeShifterNumber = 0
    self.LineScanControlPoint_x = []
    self.LineScanControlPoint_y = []
    self.LineScanControlPoint_Weights = []
    self.LineScanControlPoint_MU = []
    
    
    
