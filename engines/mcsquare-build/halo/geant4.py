"""Geant4 (OpenGATE) reference for the halo study: the same phantom and idealised beam as prepare.py.
python geant4.py ENERGY_MEV PHYSICS N THREADS SEED OUT"""
import sys
from pathlib import Path
import opengate as gate

E, physics, n, threads, seed, out = float(sys.argv[1]), sys.argv[2], int(float(sys.argv[3])), int(sys.argv[4]), int(sys.argv[5]), Path(sys.argv[6])
mm, m, MeV = gate.g4_units.mm, gate.g4_units.m, gate.g4_units.MeV
sim = gate.Simulation()
sim.g4_verbose = False; sim.number_of_threads = threads; sim.random_seed = seed; sim.output_dir = str(out)
sim.progress_bar = False; sim.check_volumes_overlap = False
sim.world.size = [1 * m, 1 * m, 1 * m]; sim.world.material = "G4_Galactic"
box = sim.add_volume("Box", "water"); box.size = [81 * mm, 81 * mm, 350 * mm]; box.material = "G4_WATER"
box.translation = [0, 0, -175 * mm]
src = sim.add_source("GenericSource", "beam"); src.particle = "proton"
src.energy.type = "mono"; src.energy.mono = E * MeV
src.position.type = "disc"; src.position.radius = 0; src.position.sigma_x = 3 * mm; src.position.sigma_y = 3 * mm
src.position.translation = [0, 0, 1 * mm]
src.direction.type = "momentum"; src.direction.momentum = [0, 0, -1]
src.n = n // threads
pm = sim.physics_manager
pm.physics_list_name = physics
pm.set_production_cut("world", "all", 1 * mm)
pm.set_production_cut(box.name, "all", 0.5 * mm)
d = sim.add_actor("DoseActor", "dose"); d.attached_to = box.name
d.size = [81, 1, 350]; d.spacing = [1 * mm, 81 * mm, 1 * mm]; d.output_filename = "halo.mhd"
d.edep.active = True
sim.add_actor("SimulationStatisticsActor", "stats")
sim.run()
print("done", E, physics, n)
