/**
 * PlanSubmissionPanel — Primary panel for treatment plan configuration and submission.
 *
 * Features:
 *  - Workflow dropdown (fetched from GET /workflows)
 *  - Dynamic parameter form (auto-rendered from workflow registry metadata)
 *  - Dose objectives editor (for optimization/robust workflows)
 *  - Robustness config section (for robust workflow only)
 *  - Job progress tracking with progress bar and status badge
 *  - QA summary display on completion
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';

// ---------------------------------------------------------------------------
// Styles (inline CSS-in-JS for portability within OHIF)
// ---------------------------------------------------------------------------

const styles = {
    panel: {
        padding: '12px',
        fontFamily: "'Inter', 'Segoe UI', sans-serif",
        fontSize: '13px',
        color: '#e0e0e0',
        backgroundColor: '#1e1e2e',
        height: '100%',
        overflowY: 'auto',
    },
    sectionTitle: {
        fontSize: '14px',
        fontWeight: 600,
        color: '#cdd6f4',
        margin: '16px 0 8px 0',
        borderBottom: '1px solid #45475a',
        paddingBottom: '4px',
        cursor: 'pointer',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    field: {
        marginBottom: '10px',
    },
    label: {
        display: 'block',
        fontSize: '11px',
        fontWeight: 500,
        color: '#a6adc8',
        marginBottom: '3px',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
    },
    input: {
        width: '100%',
        padding: '6px 8px',
        backgroundColor: '#313244',
        border: '1px solid #45475a',
        borderRadius: '4px',
        color: '#cdd6f4',
        fontSize: '13px',
        outline: 'none',
        boxSizing: 'border-box',
    },
    select: {
        width: '100%',
        padding: '6px 8px',
        backgroundColor: '#313244',
        border: '1px solid #45475a',
        borderRadius: '4px',
        color: '#cdd6f4',
        fontSize: '13px',
        outline: 'none',
        boxSizing: 'border-box',
        appearance: 'auto',
    },
    button: {
        width: '100%',
        padding: '10px',
        backgroundColor: '#89b4fa',
        color: '#1e1e2e',
        border: 'none',
        borderRadius: '6px',
        fontSize: '14px',
        fontWeight: 600,
        cursor: 'pointer',
        marginTop: '12px',
        transition: 'background-color 0.2s',
    },
    buttonDisabled: {
        backgroundColor: '#45475a',
        color: '#6c7086',
        cursor: 'not-allowed',
    },
    smallButton: {
        padding: '4px 10px',
        backgroundColor: '#45475a',
        color: '#cdd6f4',
        border: 'none',
        borderRadius: '4px',
        fontSize: '11px',
        cursor: 'pointer',
        marginLeft: '6px',
    },
    removeButton: {
        padding: '4px 8px',
        backgroundColor: '#f38ba8',
        color: '#1e1e2e',
        border: 'none',
        borderRadius: '4px',
        fontSize: '11px',
        cursor: 'pointer',
        marginLeft: '4px',
    },
    progressContainer: {
        marginTop: '12px',
        padding: '10px',
        backgroundColor: '#313244',
        borderRadius: '6px',
    },
    progressBar: {
        width: '100%',
        height: '6px',
        backgroundColor: '#45475a',
        borderRadius: '3px',
        overflow: 'hidden',
        marginTop: '6px',
    },
    progressFill: {
        height: '100%',
        backgroundColor: '#a6e3a1',
        borderRadius: '3px',
        transition: 'width 0.3s ease',
    },
    badge: {
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: '10px',
        fontSize: '11px',
        fontWeight: 600,
        textTransform: 'uppercase',
    },
    resultCard: {
        marginTop: '12px',
        padding: '10px',
        backgroundColor: '#313244',
        borderRadius: '6px',
        border: '1px solid #45475a',
    },
    resultRow: {
        display: 'flex',
        justifyContent: 'space-between',
        padding: '3px 0',
        fontSize: '12px',
    },
    objectiveRow: {
        display: 'flex',
        gap: '4px',
        alignItems: 'center',
        marginBottom: '6px',
        flexWrap: 'wrap',
    },
    objectiveInput: {
        padding: '4px 6px',
        backgroundColor: '#313244',
        border: '1px solid #45475a',
        borderRadius: '4px',
        color: '#cdd6f4',
        fontSize: '12px',
        outline: 'none',
    },
    chevron: {
        fontSize: '10px',
        transition: 'transform 0.2s',
    },
    collapsible: {
        overflow: 'hidden',
        transition: 'max-height 0.3s ease',
    },
};

const BADGE_COLORS = {
    queued: { backgroundColor: '#f9e2af', color: '#1e1e2e' },
    running: { backgroundColor: '#89b4fa', color: '#1e1e2e' },
    succeeded: { backgroundColor: '#a6e3a1', color: '#1e1e2e' },
    failed: { backgroundColor: '#f38ba8', color: '#1e1e2e' },
    cancelled: { backgroundColor: '#6c7086', color: '#cdd6f4' },
};

const OBJECTIVE_TYPES = ['DMin', 'DMax', 'DUniform', 'DVHMin', 'DVHMax'];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function DynamicParameterField({ param, value, onChange }) {
    const handleChange = (e) => {
        let val = e.target.value;
        if (param.type === 'number') val = parseFloat(val) || 0;
        if (param.type === 'integer') val = parseInt(val, 10) || 0;
        if (param.type === 'boolean') val = e.target.checked;
        onChange(param.name, val);
    };

    if (param.type === 'boolean') {
        return (
            <div style={styles.field}>
                <label style={styles.label}>
                    <input
                        type="checkbox"
                        checked={!!value}
                        onChange={handleChange}
                        style={{ marginRight: '6px' }}
                    />
                    {param.label}
                </label>
            </div>
        );
    }

    return (
        <div style={styles.field}>
            <label style={styles.label}>
                {param.label}
                {param.units && <span style={{ color: '#6c7086' }}> ({param.units})</span>}
            </label>
            <input
                type="number"
                style={styles.input}
                value={value ?? param.default ?? ''}
                onChange={handleChange}
                min={param.min_value}
                max={param.max_value}
                step={param.type === 'integer' ? 1 : 'any'}
                title={param.description || ''}
            />
        </div>
    );
}

function ObjectiveRow({ objective, index, onChange, onRemove }) {
    const update = (key, val) => {
        onChange(index, { ...objective, [key]: val });
    };

    return (
        <div style={styles.objectiveRow}>
            <input
                style={{ ...styles.objectiveInput, width: '90px' }}
                placeholder="ROI name"
                value={objective.structure_name || ''}
                onChange={(e) => update('structure_name', e.target.value)}
            />
            <select
                style={{ ...styles.objectiveInput, width: '80px' }}
                value={objective.objective_type || 'DUniform'}
                onChange={(e) => update('objective_type', e.target.value)}
            >
                {OBJECTIVE_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                ))}
            </select>
            <input
                style={{ ...styles.objectiveInput, width: '55px' }}
                type="number"
                placeholder="Dose"
                value={objective.dose_gy ?? ''}
                onChange={(e) => update('dose_gy', parseFloat(e.target.value) || 0)}
            />
            <input
                style={{ ...styles.objectiveInput, width: '45px' }}
                type="number"
                placeholder="Wt"
                value={objective.weight ?? 1.0}
                onChange={(e) => update('weight', parseFloat(e.target.value) || 1.0)}
            />
            {(objective.objective_type === 'DVHMin' || objective.objective_type === 'DVHMax') && (
                <input
                    style={{ ...styles.objectiveInput, width: '45px' }}
                    type="number"
                    step="0.01"
                    placeholder="Vol"
                    value={objective.volume_fraction ?? ''}
                    onChange={(e) => update('volume_fraction', parseFloat(e.target.value) || 0)}
                />
            )}
            <button style={styles.removeButton} onClick={() => onRemove(index)}>✕</button>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main Panel
// ---------------------------------------------------------------------------

function PlanSubmissionPanel({ commandsManager, servicesManager }) {
    // Workflow state
    const [workflows, setWorkflows] = useState([]);
    const [selectedWorkflowId, setSelectedWorkflowId] = useState('');
    const [workflowDetail, setWorkflowDetail] = useState(null);

    // Plan fields
    const [prescriptionGy, setPrescriptionGy] = useState(2.0);
    const [beamCount, setBeamCount] = useState(1);
    const [fractionCount, setFractionCount] = useState(1);
    const [notes, setNotes] = useState('');
    const [dynamicParams, setDynamicParams] = useState({});

    // Objectives (Phase 8A)
    const [objectives, setObjectives] = useState([]);

    // Robustness (Phase 8C)
    const [robustness, setRobustness] = useState({
        setup_systematic_error_mm: [1.6, 1.6, 1.6],
        setup_random_error_mm: [0.0, 0.0, 0.0],
        range_systematic_error_pct: 5.0,
        selection_strategy: 'REDUCED_SET',
        num_scenarios: 5,
    });

    // Job tracking
    const [jobId, setJobId] = useState(null);
    const [planId, setPlanId] = useState(null);
    const [jobState, setJobState] = useState(null);
    const [jobProgress, setJobProgress] = useState(0);
    const [jobStage, setJobStage] = useState('');
    const [jobEta, setJobEta] = useState(null);
    const [qaResult, setQaResult] = useState(null);
    const [error, setError] = useState(null);

    // Section collapse state
    const [sectionsOpen, setSectionsOpen] = useState({
        config: true,
        objectives: false,
        robustness: false,
    });

    const isSubmitting = useRef(false);

    // ---- Fetch workflows on mount ----
    useEffect(() => {
        async function fetchWorkflows() {
            try {
                const wfs = await commandsManager.runCommand('radiarch.fetchWorkflows');
                if (Array.isArray(wfs) && wfs.length > 0) {
                    setWorkflows(wfs);
                    setSelectedWorkflowId(wfs[0].id);
                }
            } catch (err) {
                console.error('Failed to fetch workflows:', err);
            }
        }
        fetchWorkflows();
    }, [commandsManager]);

    // ---- Fetch workflow detail on selection change ----
    useEffect(() => {
        if (!selectedWorkflowId) return;
        async function fetchDetail() {
            try {
                const detail = await commandsManager.runCommand('radiarch.fetchWorkflowDetail', {
                    workflowId: selectedWorkflowId,
                });
                setWorkflowDetail(detail);
                // Initialize dynamic params with defaults
                if (detail?.default_parameters) {
                    const defaults = {};
                    detail.default_parameters.forEach((p) => {
                        defaults[p.name] = p.default;
                    });
                    setDynamicParams(defaults);
                }
            } catch (err) {
                console.error('Failed to fetch workflow detail:', err);
            }
        }
        fetchDetail();
    }, [selectedWorkflowId, commandsManager]);

    // ---- Helpers ----
    const toggleSection = (section) => {
        setSectionsOpen((prev) => ({ ...prev, [section]: !prev[section] }));
    };

    const isOptimizationWorkflow = workflowDetail?.category === 'optimization' || workflowDetail?.category === 'robust';
    const isRobustWorkflow = workflowDetail?.category === 'robust';

    const handleDynamicParamChange = useCallback((name, value) => {
        setDynamicParams((prev) => ({ ...prev, [name]: value }));
    }, []);

    const addObjective = () => {
        setObjectives((prev) => [
            ...prev,
            { structure_name: 'PTV', objective_type: 'DUniform', dose_gy: prescriptionGy, weight: 1.0 },
        ]);
    };

    const updateObjective = (index, updated) => {
        setObjectives((prev) => prev.map((o, i) => (i === index ? updated : o)));
    };

    const removeObjective = (index) => {
        setObjectives((prev) => prev.filter((_, i) => i !== index));
    };

    const updateRobustness = (key, value) => {
        setRobustness((prev) => ({ ...prev, [key]: value }));
    };

    // ---- Submit ----
    const handleSubmit = async () => {
        if (isSubmitting.current) return;
        isSubmitting.current = true;
        setError(null);
        setQaResult(null);
        setJobState(null);
        setJobProgress(0);
        setJobStage('');

        try {
            // Get study UID from OHIF context if available
            let studyInstanceUid = '1.2.3.4.5.6.7.8.9';
            try {
                const { activeStudy } = servicesManager?.services?.DisplaySetService || {};
                if (activeStudy?.StudyInstanceUID) {
                    studyInstanceUid = activeStudy.StudyInstanceUID;
                }
            } catch (_) { /* fallback to dummy UID */ }

            const submitPayload = {
                studyInstanceUid,
                workflowId: selectedWorkflowId,
                prescriptionGy,
                beamCount,
                fractionCount,
                notes: notes || null,
                ...dynamicParams,
            };

            if (isOptimizationWorkflow && objectives.length > 0) {
                submitPayload.objectives = objectives;
            }
            if (isRobustWorkflow) {
                submitPayload.robustness = robustness;
            }

            const planData = await commandsManager.runCommand('radiarch.submitPlan', submitPayload);

            if (!planData?.id || !planData?.job_id) {
                setError('Failed to create plan — no ID returned');
                return;
            }

            setPlanId(planData.id);
            setJobId(planData.job_id);
            setJobState('queued');

            // Poll job
            const finalJob = await commandsManager.runCommand('radiarch.pollJob', {
                jobId: planData.job_id,
                onProgress: ({ state, progress, stage, etaSeconds }) => {
                    setJobState(state);
                    setJobProgress(progress || 0);
                    setJobStage(stage || '');
                    setJobEta(etaSeconds);
                },
            });

            setJobState(finalJob?.state || 'unknown');
            setJobProgress(1.0);

            if (finalJob?.state === 'succeeded') {
                const planResult = await commandsManager.runCommand('radiarch.loadPlanResult', {
                    planId: planData.id,
                });
                setQaResult(planResult?.qa_summary || null);
            }
        } catch (err) {
            setError(err.message || 'Plan submission failed');
            setJobState('failed');
        } finally {
            isSubmitting.current = false;
        }
    };

    // ---- Render ----
    return (
        <div style={styles.panel}>
            <h3 style={{ margin: '0 0 12px 0', color: '#cdd6f4', fontSize: '16px' }}>
                ⚛ Treatment Plan
            </h3>

            {/* Section 1: Plan Configuration */}
            <div
                style={styles.sectionTitle}
                onClick={() => toggleSection('config')}
            >
                <span>Plan Configuration</span>
                <span style={{ ...styles.chevron, transform: sectionsOpen.config ? 'rotate(90deg)' : 'rotate(0deg)' }}>▶</span>
            </div>
            {sectionsOpen.config && (
                <div>
                    {/* Workflow selector */}
                    <div style={styles.field}>
                        <label style={styles.label}>Workflow</label>
                        <select
                            style={styles.select}
                            value={selectedWorkflowId}
                            onChange={(e) => setSelectedWorkflowId(e.target.value)}
                        >
                            {workflows.map((wf) => (
                                <option key={wf.id} value={wf.id}>
                                    {wf.name} ({wf.category})
                                </option>
                            ))}
                        </select>
                        {workflowDetail && (
                            <div style={{ fontSize: '11px', color: '#6c7086', marginTop: '4px' }}>
                                {workflowDetail.modality} · {workflowDetail.engine}
                            </div>
                        )}
                    </div>

                    {/* Core fields */}
                    <div style={styles.field}>
                        <label style={styles.label}>Prescription Dose (Gy)</label>
                        <input
                            type="number"
                            style={styles.input}
                            value={prescriptionGy}
                            onChange={(e) => setPrescriptionGy(parseFloat(e.target.value) || 0)}
                            min={0.1}
                            step={0.1}
                        />
                    </div>
                    <div style={styles.field}>
                        <label style={styles.label}>Beam Count</label>
                        <input
                            type="range"
                            min={1}
                            max={9}
                            value={beamCount}
                            onChange={(e) => setBeamCount(parseInt(e.target.value, 10))}
                            style={{ width: '100%' }}
                        />
                        <div style={{ fontSize: '11px', color: '#6c7086', textAlign: 'center' }}>
                            {beamCount} beam{beamCount > 1 ? 's' : ''} · {Array.from({ length: beamCount }, (_, i) =>
                                `${Math.round(i * (360 / beamCount))}°`
                            ).join(', ')}
                        </div>
                    </div>
                    <div style={styles.field}>
                        <label style={styles.label}>Fractions</label>
                        <input
                            type="number"
                            style={styles.input}
                            value={fractionCount}
                            onChange={(e) => setFractionCount(parseInt(e.target.value, 10) || 1)}
                            min={1}
                            max={50}
                        />
                    </div>

                    {/* Dynamic workflow parameters */}
                    {workflowDetail?.default_parameters?.length > 0 && (
                        <>
                            <div style={{ ...styles.label, marginTop: '12px', fontSize: '10px', color: '#89b4fa' }}>
                                {workflowDetail.name} Parameters
                            </div>
                            {workflowDetail.default_parameters.map((param) => (
                                <DynamicParameterField
                                    key={param.name}
                                    param={param}
                                    value={dynamicParams[param.name]}
                                    onChange={handleDynamicParamChange}
                                />
                            ))}
                        </>
                    )}

                    {/* Notes */}
                    <div style={styles.field}>
                        <label style={styles.label}>Notes</label>
                        <textarea
                            style={{ ...styles.input, minHeight: '40px', resize: 'vertical' }}
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            placeholder="Optional notes..."
                        />
                    </div>
                </div>
            )}

            {/* Section 2: Dose Objectives (optimization/robust only) */}
            {isOptimizationWorkflow && (
                <>
                    <div
                        style={styles.sectionTitle}
                        onClick={() => toggleSection('objectives')}
                    >
                        <span>Dose Objectives</span>
                        <span style={{ ...styles.chevron, transform: sectionsOpen.objectives ? 'rotate(90deg)' : 'rotate(0deg)' }}>▶</span>
                    </div>
                    {sectionsOpen.objectives && (
                        <div>
                            {objectives.map((obj, i) => (
                                <ObjectiveRow
                                    key={i}
                                    objective={obj}
                                    index={i}
                                    onChange={updateObjective}
                                    onRemove={removeObjective}
                                />
                            ))}
                            <button style={styles.smallButton} onClick={addObjective}>+ Add Objective</button>
                            <div style={{ fontSize: '10px', color: '#6c7086', marginTop: '4px' }}>
                                Structure · Type · Dose(Gy) · Weight · [Volume]
                            </div>
                        </div>
                    )}
                </>
            )}

            {/* Section 3: Robustness (robust workflow only) */}
            {isRobustWorkflow && (
                <>
                    <div
                        style={styles.sectionTitle}
                        onClick={() => toggleSection('robustness')}
                    >
                        <span>Robustness Configuration</span>
                        <span style={{ ...styles.chevron, transform: sectionsOpen.robustness ? 'rotate(90deg)' : 'rotate(0deg)' }}>▶</span>
                    </div>
                    {sectionsOpen.robustness && (
                        <div>
                            <div style={styles.field}>
                                <label style={styles.label}>Setup Systematic Error (mm) [x, y, z]</label>
                                <div style={{ display: 'flex', gap: '4px' }}>
                                    {[0, 1, 2].map((axis) => (
                                        <input
                                            key={axis}
                                            type="number"
                                            style={{ ...styles.input, flex: 1 }}
                                            value={robustness.setup_systematic_error_mm[axis]}
                                            onChange={(e) => {
                                                const arr = [...robustness.setup_systematic_error_mm];
                                                arr[axis] = parseFloat(e.target.value) || 0;
                                                updateRobustness('setup_systematic_error_mm', arr);
                                            }}
                                            step={0.1}
                                        />
                                    ))}
                                </div>
                            </div>
                            <div style={styles.field}>
                                <label style={styles.label}>Setup Random Error (mm) [x, y, z]</label>
                                <div style={{ display: 'flex', gap: '4px' }}>
                                    {[0, 1, 2].map((axis) => (
                                        <input
                                            key={axis}
                                            type="number"
                                            style={{ ...styles.input, flex: 1 }}
                                            value={robustness.setup_random_error_mm[axis]}
                                            onChange={(e) => {
                                                const arr = [...robustness.setup_random_error_mm];
                                                arr[axis] = parseFloat(e.target.value) || 0;
                                                updateRobustness('setup_random_error_mm', arr);
                                            }}
                                            step={0.1}
                                        />
                                    ))}
                                </div>
                            </div>
                            <div style={styles.field}>
                                <label style={styles.label}>Range Systematic Error (%)</label>
                                <input
                                    type="number"
                                    style={styles.input}
                                    value={robustness.range_systematic_error_pct}
                                    onChange={(e) => updateRobustness('range_systematic_error_pct', parseFloat(e.target.value) || 0)}
                                    min={0}
                                    max={20}
                                    step={0.5}
                                />
                            </div>
                            <div style={styles.field}>
                                <label style={styles.label}>Selection Strategy</label>
                                <select
                                    style={styles.select}
                                    value={robustness.selection_strategy}
                                    onChange={(e) => updateRobustness('selection_strategy', e.target.value)}
                                >
                                    <option value="REDUCED_SET">Reduced Set</option>
                                    <option value="ALL">All</option>
                                    <option value="RANDOM">Random</option>
                                </select>
                            </div>
                            <div style={styles.field}>
                                <label style={styles.label}>Number of Scenarios</label>
                                <input
                                    type="number"
                                    style={styles.input}
                                    value={robustness.num_scenarios}
                                    onChange={(e) => updateRobustness('num_scenarios', parseInt(e.target.value, 10) || 5)}
                                    min={1}
                                    max={21}
                                />
                            </div>
                        </div>
                    )}
                </>
            )}

            {/* Submit Button */}
            <button
                style={{
                    ...styles.button,
                    ...(isSubmitting.current ? styles.buttonDisabled : {}),
                }}
                onClick={handleSubmit}
                disabled={isSubmitting.current}
            >
                {isSubmitting.current ? '⏳ Submitting...' : '▶ Submit Plan'}
            </button>

            {/* Error */}
            {error && (
                <div style={{ marginTop: '8px', padding: '8px', backgroundColor: '#45263e', borderRadius: '4px', color: '#f38ba8', fontSize: '12px' }}>
                    ⚠ {error}
                </div>
            )}

            {/* Job Progress */}
            {jobState && (
                <div style={styles.progressContainer}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ ...styles.badge, ...(BADGE_COLORS[jobState] || {}) }}>
                            {jobState}
                        </span>
                        {jobStage && <span style={{ fontSize: '11px', color: '#a6adc8' }}>{jobStage}</span>}
                    </div>
                    <div style={styles.progressBar}>
                        <div
                            style={{ ...styles.progressFill, width: `${Math.round(jobProgress * 100)}%` }}
                        />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#6c7086', marginTop: '4px' }}>
                        <span>{Math.round(jobProgress * 100)}%</span>
                        {jobEta != null && jobEta > 0 && <span>ETA: {Math.round(jobEta)}s</span>}
                    </div>
                </div>
            )}

            {/* QA Result Card */}
            {qaResult && (
                <div style={styles.resultCard}>
                    <div style={{ ...styles.label, color: '#a6e3a1', marginBottom: '6px' }}>QA Summary</div>
                    {Object.entries(qaResult).map(([key, value]) => {
                        if (key === 'dvh' || typeof value === 'object') return null;
                        return (
                            <div key={key} style={styles.resultRow}>
                                <span style={{ color: '#a6adc8' }}>{key}</span>
                                <span style={{ color: '#cdd6f4', fontWeight: 500 }}>
                                    {typeof value === 'number' ? value.toFixed(4) : String(value)}
                                </span>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

// OHIF Panel configuration
PlanSubmissionPanel.panelConfig = {
    id: 'radiarch-plan-submission',
    label: 'Treatment Plan',
    iconName: 'settings', // OHIF built-in icon
};

export default PlanSubmissionPanel;
