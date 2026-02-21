
import numpy as np
from scipy import ndimage as nd
import math
import ctypes


def WET_raytracing(SPR, beam_direction, ROI=[]):

  try:
    # import C library
    libRaytracing = ctypes.cdll.LoadLibrary("Process/C_libraries/libRayTracing.so")
    float_array = np.ctypeslib.ndpointer(dtype=np.float32)
    int_array = np.ctypeslib.ndpointer(dtype=np.int32)
    bool_array = np.ctypeslib.ndpointer(dtype=np.bool)
    libRaytracing.raytrace_WET.argtypes = [float_array, bool_array, float_array, float_array, float_array, int_array, float_array]
    libRaytracing.raytrace_WET.restype  = ctypes.c_void_p

    # prepare inputs for C library
    Offset = np.array(SPR.ImagePositionPatient, dtype=np.float32, order='C')
    PixelSpacing = np.array(SPR.PixelSpacing, dtype=np.float32, order='C')
    GridSize = np.array(SPR.GridSize, dtype=np.int32, order='C')
    beam_direction = np.array(beam_direction, dtype=np.float32, order='C')
    WET = np.zeros(SPR.GridSize, dtype=np.float32, order='C')
    if(ROI == []):
      ROI_mask = np.ones(SPR.GridSize)
    else:
      ROI_mask = ROI.Mask

    # call C function
    libRaytracing.raytrace_WET(SPR.Image.astype(np.float32), ROI_mask.astype(np.bool), WET, Offset, PixelSpacing, GridSize, beam_direction)


  except:
    print("Warning: Raytracing is performed with the Python implementation instead of libRayTracing. The computation will be much slower.")
    Voxel_Coord_X = SPR.ImagePositionPatient[0] + np.arange(SPR.GridSize[0])*SPR.PixelSpacing[0]
    Voxel_Coord_Y = SPR.ImagePositionPatient[1] + np.arange(SPR.GridSize[1])*SPR.PixelSpacing[1]
    Voxel_Coord_Z = SPR.ImagePositionPatient[2] + np.arange(SPR.GridSize[2])*SPR.PixelSpacing[2]
    u = -beam_direction[0]
    v = -beam_direction[1]
    w = -beam_direction[2]

    WET = np.zeros(SPR.GridSize)

    for i in range(SPR.GridSize[0]):
      for j in range(SPR.GridSize[1]):
        for k in range(SPR.GridSize[2]):
          if(ROI != []):
            if(ROI.Mask[j,i,k] == 0): continue

          # initialize raytracing for voxel ijk
          voxel_WET = 0
          x = Voxel_Coord_X[i] + 0.5 * SPR.PixelSpacing[0]
          y = Voxel_Coord_Y[j] + 0.5 * SPR.PixelSpacing[1]
          z = Voxel_Coord_Z[k] + 0.5 * SPR.PixelSpacing[2]
          dist = np.array([1.0, 1.0, 1.0])

          # raytracing loop
          while True:
            # check if we are still inside the SPR image
            if(x < Voxel_Coord_X[0] and u < 0): break
            if(x > Voxel_Coord_X[-1] and u > 0): break
            if(y < Voxel_Coord_Y[0] and v < 0): break
            if(y > Voxel_Coord_Y[-1] and v > 0): break
            if(z < Voxel_Coord_Z[0] and w < 0): break
            if(z > Voxel_Coord_Z[-1] and w > 0): break

            # compute distante to next voxel
            dist[0] = abs(((math.floor((x-SPR.ImagePositionPatient[0])/SPR.PixelSpacing[0]) + float(u>0)) * SPR.PixelSpacing[0] + SPR.ImagePositionPatient[0] - x)/u)
            dist[1] = abs(((math.floor((y-SPR.ImagePositionPatient[1])/SPR.PixelSpacing[1]) + float(v>0)) * SPR.PixelSpacing[1] + SPR.ImagePositionPatient[1] - y)/v)
            dist[2] = abs(((math.floor((z-SPR.ImagePositionPatient[2])/SPR.PixelSpacing[2]) + float(w>0)) * SPR.PixelSpacing[2] + SPR.ImagePositionPatient[2] - z)/w)
            step = dist.min() + 1e-3
            
            # accumulate WET
            voxel_SPR = SPR.get_SPR_at_position([x,y,z])
            voxel_WET += voxel_SPR * step

            # update position
            x = x + step * u
            y = y + step * v
            z = z + step * w

          WET[j,i,k] = voxel_WET


  return WET


