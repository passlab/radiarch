/**
 * Radiarch OHIF v3 Extension
 *
 * Registers the RadiarchClient service, 4 panel modules, and commands module
 * for treatment plan submission, dose visualization, DVH display, and
 * delivery simulation — exposing all Phase 8 features.
 */

import RadiarchClient from './services/RadiarchClient';
import commandsModule from './commandsModule';
import PlanSubmissionPanel from './panels/PlanSubmissionPanel';
import DVHPanel from './panels/DVHPanel';
import DoseOverlayPanel from './panels/DoseOverlayPanel';
import SimulationPanel from './panels/SimulationPanel';
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

    getPanelModule({ servicesManager, commandsManager }) {
        return [
            {
                name: 'radiarch-plan-submission',
                iconName: 'settings',
                iconLabel: 'Treatment Plan',
                label: 'Treatment Plan',
                component: (props) =>
                    PlanSubmissionPanel({
                        ...props,
                        commandsManager,
                        servicesManager,
                    }),
            },
            {
                name: 'radiarch-dvh',
                iconName: 'chart',
                iconLabel: 'DVH',
                label: 'DVH',
                component: (props) =>
                    DVHPanel({
                        ...props,
                        commandsManager,
                        servicesManager,
                    }),
            },
            {
                name: 'radiarch-dose-overlay',
                iconName: 'viewport-window-level',
                iconLabel: 'Dose Overlay',
                label: 'Dose Overlay',
                component: (props) =>
                    DoseOverlayPanel({
                        ...props,
                        commandsManager,
                    }),
            },
            {
                name: 'radiarch-simulation',
                iconName: 'tool-calibration',
                iconLabel: 'Simulation',
                label: 'Simulation',
                component: (props) =>
                    SimulationPanel({
                        ...props,
                        commandsManager,
                    }),
            },
        ];
    },

    getCommandsModule({ servicesManager, commandsManager }) {
        return commandsModule({ servicesManager, commandsManager });
    },
};

export default extension;
