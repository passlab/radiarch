/**
 * RadiarchClient — JavaScript HTTP client for the Radiarch TPS API.
 *
 * Mirrors MONAILabel's MonaiLabelClient.js pattern: thin axios wrappers
 * for each endpoint, plus a pollJob() convenience method.
 *
 * Usage:
 *   import RadiarchClient from './services/RadiarchClient';
 *   const client = new RadiarchClient('http://localhost:8000/api/v1');
 *   const info = await client.info();
 *   const plan = await client.createPlan({ ... });
 *   const job = await client.pollJob(plan.job_id);
 */

import axios from 'axios';

export default class RadiarchClient {
    constructor(serverUrl) {
        this.serverUrl = serverUrl.replace(/\/$/, '');
    }

    // ---- Info & Workflows ----

    async info() {
        return RadiarchClient.apiGet(`${this.serverUrl}/info`);
    }

    async listWorkflows() {
        return RadiarchClient.apiGet(`${this.serverUrl}/workflows`);
    }

    async getWorkflow(workflowId) {
        return RadiarchClient.apiGet(
            `${this.serverUrl}/workflows/${encodeURIComponent(workflowId)}`
        );
    }

    // ---- Plans ----

    async createPlan({
        studyInstanceUid,
        prescriptionGy,
        workflowId = 'proton-impt-basic',
        fractionCount = 1,
        beamCount = 1,
        segmentationUid = null,
        notes = null,
    }) {
        const payload = {
            study_instance_uid: studyInstanceUid,
            prescription_gy: prescriptionGy,
            workflow_id: workflowId,
            fraction_count: fractionCount,
            beam_count: beamCount,
        };
        if (segmentationUid) payload.segmentation_uid = segmentationUid;
        if (notes) payload.notes = notes;

        return RadiarchClient.apiPost(`${this.serverUrl}/plans`, payload);
    }

    async getPlan(planId) {
        return RadiarchClient.apiGet(
            `${this.serverUrl}/plans/${encodeURIComponent(planId)}`
        );
    }

    async listPlans() {
        return RadiarchClient.apiGet(`${this.serverUrl}/plans`);
    }

    async deletePlan(planId) {
        return RadiarchClient.apiDelete(
            `${this.serverUrl}/plans/${encodeURIComponent(planId)}`
        );
    }

    // ---- Jobs ----

    async getJob(jobId) {
        return RadiarchClient.apiGet(
            `${this.serverUrl}/jobs/${encodeURIComponent(jobId)}`
        );
    }

    /**
     * Poll a job until it reaches a terminal state.
     * @param {string} jobId
     * @param {number} timeoutMs - max wait time in milliseconds (default 300000 = 5min)
     * @param {number} intervalMs - poll interval in milliseconds (default 2000)
     * @returns {Promise<object>} final job status
     */
    async pollJob(jobId, timeoutMs = 300000, intervalMs = 2000) {
        const terminal = new Set(['succeeded', 'failed', 'cancelled']);
        const deadline = Date.now() + timeoutMs;

        while (Date.now() < deadline) {
            const resp = await this.getJob(jobId);
            if (resp && resp.data && terminal.has(resp.data.state)) {
                return resp;
            }
            await new Promise((resolve) => setTimeout(resolve, intervalMs));
        }
        throw new Error(`Job ${jobId} did not complete within ${timeoutMs}ms`);
    }

    // ---- Artifacts ----

    async getArtifact(artifactId) {
        return RadiarchClient.apiGet(
            `${this.serverUrl}/artifacts/${encodeURIComponent(artifactId)}`,
            'arraybuffer'
        );
    }

    // ---- Sessions ----

    async createSession(file) {
        const formData = new FormData();
        formData.append('file', file);
        return RadiarchClient.apiPostData(
            `${this.serverUrl}/sessions`,
            formData,
            'json'
        );
    }

    async getSession(sessionId) {
        return RadiarchClient.apiGet(
            `${this.serverUrl}/sessions/${encodeURIComponent(sessionId)}`
        );
    }

    async deleteSession(sessionId) {
        return RadiarchClient.apiDelete(
            `${this.serverUrl}/sessions/${encodeURIComponent(sessionId)}`
        );
    }

    // ---- Static HTTP helpers ----

    static apiGet(url, responseType = 'json') {
        console.debug('RadiarchClient GET:', url);
        return axios
            .get(url, { responseType })
            .then((response) => response)
            .catch((error) => {
                console.error('RadiarchClient GET error:', error);
                return error;
            });
    }

    static apiPost(url, data, responseType = 'json') {
        console.debug('RadiarchClient POST:', url);
        return axios
            .post(url, data, {
                responseType,
                headers: { 'Content-Type': 'application/json' },
            })
            .then((response) => response)
            .catch((error) => {
                console.error('RadiarchClient POST error:', error);
                return error;
            });
    }

    static apiPostData(url, data, responseType = 'json') {
        console.debug('RadiarchClient POST (form):', url);
        return axios
            .post(url, data, { responseType })
            .then((response) => response)
            .catch((error) => {
                console.error('RadiarchClient POST error:', error);
                return error;
            });
    }

    static apiDelete(url) {
        console.debug('RadiarchClient DELETE:', url);
        return axios
            .delete(url)
            .then((response) => response)
            .catch((error) => {
                console.error('RadiarchClient DELETE error:', error);
                return error;
            });
    }
}
