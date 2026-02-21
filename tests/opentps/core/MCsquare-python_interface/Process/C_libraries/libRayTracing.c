#include <stdio.h>
#include <stdlib.h>
#include <math.h> 
#include <stdbool.h>
#include <omp.h>


void raytrace_WET(float *SPR, bool *ROI_mask, float *WET, float *Offset, float *PixelSpacing, int *GridSize, float *beam_direction){
  float *Voxel_Coord_X = (float*) malloc(GridSize[0] * sizeof(float));
  float *Voxel_Coord_Y = (float*) malloc(GridSize[1] * sizeof(float));
  float *Voxel_Coord_Z = (float*) malloc(GridSize[2] * sizeof(float));
  for(int i=0; i<GridSize[0]; i++) Voxel_Coord_X[i] = Offset[0] + i * PixelSpacing[0];
  for(int i=0; i<GridSize[1]; i++) Voxel_Coord_Y[i] = Offset[1] + i * PixelSpacing[1];
  for(int i=0; i<GridSize[2]; i++) Voxel_Coord_Z[i] = Offset[2] + i * PixelSpacing[2];
  
  float u = -beam_direction[0];
  float v = -beam_direction[1];
  float w = -beam_direction[2];

  for(int i=0; i<GridSize[0]; i++){
    for(int j=0; j<GridSize[1]; j++){
      #pragma omp parallel for
      for(int k=0; k<GridSize[2]; k++){

        int id_vox = k + GridSize[2] * (i + GridSize[1]*j); //order='C'
        if(ROI_mask[id_vox] == 0) continue;

        // initialize raytracing for voxel ijk
        float x = Voxel_Coord_X[i] + 0.5*PixelSpacing[0];
        float y = Voxel_Coord_Y[j] + 0.5*PixelSpacing[1];
        float z = Voxel_Coord_Z[k] + 0.5*PixelSpacing[2];
        float dist[3] = {1.0, 1.0, 1.0};
        float voxel_SPR, step;
        int id_x, id_y, id_z, id_SPR;

        // raytracing loop
        while(true){
          // check if we are still inside the SPR image
          if(x < Voxel_Coord_X[0] && u < 0) break;
          if(x > Voxel_Coord_X[GridSize[0]-1] && u > 0) break;
          if(y < Voxel_Coord_Y[0] && v < 0) break;
          if(y > Voxel_Coord_Y[GridSize[1]-1] && v > 0) break;
          if(z < Voxel_Coord_Z[0] && w < 0) break;
          if(z > Voxel_Coord_Z[GridSize[2]-1] && w > 0) break;

          // compute distante to next voxel
          dist[0] = fabs(((floor((x-Offset[0])/PixelSpacing[0]) + (u>0)) * PixelSpacing[0] + Offset[0] - x)/u);
          dist[1] = fabs(((floor((y-Offset[1])/PixelSpacing[1]) + (v>0)) * PixelSpacing[1] + Offset[1] - y)/v);
          dist[2] = fabs(((floor((z-Offset[2])/PixelSpacing[2]) + (w>0)) * PixelSpacing[2] + Offset[2] - z)/w);
          step = fmin(dist[0], fmin(dist[1], dist[2])) + 1e-3;

          // compute voxel index from position
          id_x = floor((x - Offset[0]) / PixelSpacing[0]);
          id_y = floor((y - Offset[1]) / PixelSpacing[1]);
          id_z = floor((z - Offset[2]) / PixelSpacing[2]);
          id_SPR = id_z + GridSize[2] * (id_x + GridSize[1]*id_y); //order='C'
          //id_SPR = id_y + GridSize[0] * (id_y + GridSize[1]*id_z); //order='F'
      
          // accumulate WET
          voxel_SPR = SPR[id_SPR];
          WET[id_vox] += voxel_SPR * step;

          // update position
          x = x + step * u;
          y = y + step * v;
          z = z + step * w;

        }
      }
    }
  }

  free(Voxel_Coord_X);
  free(Voxel_Coord_Y);
  free(Voxel_Coord_Z);

}


