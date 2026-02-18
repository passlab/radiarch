/**
 * Radiarch OHIF v3 Extension
 *
 * Registers the RadiarchClient service and (future) panel modules
 * for treatment plan submission, dose overlay, and DVH display.
 *
 * Based on MONAILabel's plugins/ohifv3/ extension template.
 */

import RadiarchClient from './services/RadiarchClient';
import EXTENSION_ID from './id';

const defaultConfig = {
    radiarchServerUrl: 'http://localhost:8000/api/v1',
};

const extension = {
    id: EXTENSION_ID,

    getServiceModule({ configuration = {} }) {
        const config = { ...defaultConfig, ...configuration };
        const client = new RadiarchClient(config.radiarchServerUrl);

        return [
            {
                name: 'RadiarchClientService',
                create: () => client,
            },
        ];
    },

    /**
     * Panel module — placeholder for future React panels:
     * - PlanSubmissionPanel: workflow selection, prescription, beam config
     * - DoseOverlayPanel: RTDOSE visualization controls
     * - DVHPanel: dose-volume histogram chart
     */
    getPanelModule() {
        return [];
    },

    /**
     * Commands module — placeholder for future commands:
     * - submitPlan: create plan from current study
     * - refreshJob: poll job status
     * - loadDose: fetch and overlay RTDOSE
     */
    getCommandsModule() {
        return [];
    },
};

export default extension;
