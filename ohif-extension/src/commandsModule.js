/**
 * Commands Module — bridges OHIF UI (panels, toolbar) with the RadiarchClient service.
 *
 * Each command is registered with OHIF's commandsManager and can be invoked
 * from panels, toolbar buttons, or keyboard shortcuts.
 */

const COMMANDS_MODULE_ID = 'radiarch-commands';

/**
 * @param {object} params
 * @param {object} params.servicesManager - OHIF ServicesManager
 * @param {object} params.commandsManager - OHIF CommandsManager
 */
function commandsModule({ servicesManager, commandsManager }) {
    /**
     * Get the RadiarchClientService from OHIF's service registry.
     */
    function getClient() {
        const { RadiarchClientService } = servicesManager.services;
        if (!RadiarchClientService) {
            throw new Error('RadiarchClientService is not registered. Ensure the Radiarch extension is loaded.');
        }
        return RadiarchClientService;
    }

    const definitions = {
        // ----------------------------------------------------------------
        // Workflow discovery
        // ----------------------------------------------------------------
        'radiarch.fetchWorkflows': {
            commandFn: async () => {
                const client = getClient();
                const resp = await client.listWorkflows();
                return resp?.data || [];
            },
        },

        'radiarch.fetchWorkflowDetail': {
            commandFn: async ({ workflowId }) => {
                const client = getClient();
                const resp = await client.getWorkflow(workflowId);
                return resp?.data || null;
            },
        },

        // ----------------------------------------------------------------
        // Plan lifecycle
        // ----------------------------------------------------------------
        'radiarch.submitPlan': {
            commandFn: async ({
                studyInstanceUid,
                workflowId,
                prescriptionGy,
                beamCount = 1,
                fractionCount = 1,
                notes = null,
                objectives = null,
                robustness = null,
                // Dynamic per-workflow parameters
                optimizationMethod,
                maxIterations,
                spotSpacingMm,
                layerSpacingMm,
                nbPrimaries,
                nbPrimariesFinal,
                muPerBeam,
                jawOpeningMm,
                segmentationUid = null,
            }) => {
                const client = getClient();

                const payload = {
                    studyInstanceUid,
                    prescriptionGy,
                    workflowId,
                    fractionCount,
                    beamCount,
                };

                // Optional fields — only include if provided
                if (segmentationUid) payload.segmentationUid = segmentationUid;
                if (notes) payload.notes = notes;
                if (objectives && objectives.length > 0) payload.objectives = objectives;
                if (robustness) payload.robustness = robustness;

                // Per-workflow parameters
                if (optimizationMethod) payload.optimizationMethod = optimizationMethod;
                if (maxIterations) payload.maxIterations = maxIterations;
                if (spotSpacingMm) payload.spotSpacingMm = spotSpacingMm;
                if (layerSpacingMm) payload.layerSpacingMm = layerSpacingMm;
                if (nbPrimaries) payload.nbPrimaries = nbPrimaries;
                if (nbPrimariesFinal) payload.nbPrimariesFinal = nbPrimariesFinal;
                if (muPerBeam) payload.muPerBeam = muPerBeam;
                if (jawOpeningMm) payload.jawOpeningMm = jawOpeningMm;

                const resp = await client.createPlan(payload);
                return resp?.data || null;
            },
        },

        'radiarch.pollJob': {
            commandFn: async ({ jobId, onProgress, timeoutMs = 300000, intervalMs = 2000 }) => {
                const client = getClient();
                const terminal = new Set(['succeeded', 'failed', 'cancelled']);
                const deadline = Date.now() + timeoutMs;

                while (Date.now() < deadline) {
                    const resp = await client.getJob(jobId);
                    const job = resp?.data;

                    if (onProgress && job) {
                        onProgress({
                            state: job.state,
                            progress: job.progress,
                            stage: job.stage,
                            message: job.message,
                            etaSeconds: job.eta_seconds,
                        });
                    }

                    if (job && terminal.has(job.state)) {
                        return job;
                    }

                    await new Promise((resolve) => setTimeout(resolve, intervalMs));
                }

                throw new Error(`Job ${jobId} did not complete within ${timeoutMs}ms`);
            },
        },

        'radiarch.loadPlanResult': {
            commandFn: async ({ planId }) => {
                const client = getClient();
                const resp = await client.getPlan(planId);
                return resp?.data || null;
            },
        },

        'radiarch.loadDose': {
            commandFn: async ({ artifactId }) => {
                const client = getClient();
                const resp = await client.getArtifact(artifactId);
                // Returns ArrayBuffer of RTDOSE DICOM; caller is responsible for
                // loading into cornerstone3D for overlay rendering.
                return resp?.data || null;
            },
        },

        // ----------------------------------------------------------------
        // Simulation (Phase 8D)
        // ----------------------------------------------------------------
        'radiarch.submitSimulation': {
            commandFn: async ({
                planId,
                motionAmplitudeMm = [0, 0, 5],
                motionPeriodS = 4.0,
                deliveryTimePerSpotMs = 1.0,
                numFractions = 5,
            }) => {
                const client = getClient();
                const resp = await client.createSimulation({
                    plan_id: planId,
                    motion_amplitude_mm: motionAmplitudeMm,
                    motion_period_s: motionPeriodS,
                    delivery_time_per_spot_ms: deliveryTimePerSpotMs,
                    num_fractions: numFractions,
                });
                return resp?.data || null;
            },
        },

        'radiarch.pollSimulation': {
            commandFn: async ({ simulationId, onProgress, timeoutMs = 600000, intervalMs = 3000 }) => {
                const client = getClient();
                const terminal = new Set(['completed', 'failed']);
                const deadline = Date.now() + timeoutMs;

                while (Date.now() < deadline) {
                    const resp = await client.getSimulation(simulationId);
                    const sim = resp?.data;

                    if (onProgress && sim) {
                        onProgress({ status: sim.status, result: sim.result });
                    }

                    if (sim && terminal.has(sim.status)) {
                        return sim;
                    }

                    await new Promise((resolve) => setTimeout(resolve, intervalMs));
                }

                throw new Error(`Simulation ${simulationId} timed out after ${timeoutMs}ms`);
            },
        },
    };

    return {
        definitions,
        defaultContext: 'VIEWER',
    };
}

export default commandsModule;
export { COMMANDS_MODULE_ID };
