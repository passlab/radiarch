/**
 * SimulationPanel — Delivery simulation UI for Phase 8D.
 *
 * Allows configuring motion parameters, delivery timing, and fractionation
 * for dose delivery simulations. Requires a completed plan.
 */

import React, { useState, useRef } from 'react';

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
    header: {
        margin: '0 0 12px 0',
        color: '#cdd6f4',
        fontSize: '16px',
        fontWeight: 600,
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
    },
    sectionTitle: {
        fontSize: '11px',
        fontWeight: 600,
        color: '#89b4fa',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        marginBottom: '8px',
        marginTop: '14px',
    },
    button: {
        width: '100%',
        padding: '10px',
        backgroundColor: '#cba6f7',
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
    progressContainer: {
        marginTop: '12px',
        padding: '10px',
        backgroundColor: '#313244',
        borderRadius: '6px',
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
    hint: {
        fontSize: '10px',
        color: '#6c7086',
        marginTop: '2px',
    },
};

const BADGE_COLORS = {
    running: { backgroundColor: '#cba6f7', color: '#1e1e2e' },
    completed: { backgroundColor: '#a6e3a1', color: '#1e1e2e' },
    failed: { backgroundColor: '#f38ba8', color: '#1e1e2e' },
};


function SimulationPanel({ commandsManager }) {
    // Input state
    const [planId, setPlanId] = useState('');
    const [motionAmplitude, setMotionAmplitude] = useState([0, 0, 5]);
    const [motionPeriod, setMotionPeriod] = useState(4.0);
    const [deliveryTimePerSpot, setDeliveryTimePerSpot] = useState(1.0);
    const [numFractions, setNumFractions] = useState(5);

    // Status state
    const [simStatus, setSimStatus] = useState(null);
    const [simResult, setSimResult] = useState(null);
    const [error, setError] = useState(null);
    const isSubmitting = useRef(false);

    const updateAmplitude = (axis, value) => {
        const arr = [...motionAmplitude];
        arr[axis] = parseFloat(value) || 0;
        setMotionAmplitude(arr);
    };

    const handleSubmit = async () => {
        if (!planId || isSubmitting.current) return;
        isSubmitting.current = true;
        setError(null);
        setSimResult(null);
        setSimStatus('running');

        try {
            const sim = await commandsManager.runCommand('radiarch.submitSimulation', {
                planId,
                motionAmplitudeMm: motionAmplitude,
                motionPeriodS: motionPeriod,
                deliveryTimePerSpotMs: deliveryTimePerSpot,
                numFractions,
            });

            if (!sim?.id) {
                setError('Failed to create simulation');
                setSimStatus('failed');
                return;
            }

            // Poll for completion
            const result = await commandsManager.runCommand('radiarch.pollSimulation', {
                simulationId: sim.id,
                onProgress: ({ status }) => setSimStatus(status),
            });

            setSimStatus(result?.status || 'completed');
            setSimResult(result?.result || result);
        } catch (err) {
            setError(err.message || 'Simulation failed');
            setSimStatus('failed');
        } finally {
            isSubmitting.current = false;
        }
    };

    return (
        <div style={styles.panel}>
            <h3 style={styles.header}>🔬 Delivery Simulation</h3>

            {/* Plan ID */}
            <div style={styles.field}>
                <label style={styles.label}>Plan ID</label>
                <input
                    type="text"
                    style={styles.input}
                    placeholder="Completed plan ID..."
                    value={planId}
                    onChange={(e) => setPlanId(e.target.value)}
                />
                <div style={styles.hint}>Enter the ID of a completed treatment plan</div>
            </div>



            {/* Motion Parameters */}
            <div style={styles.sectionTitle}>Motion Parameters</div>

            <div style={styles.field}>
                <label style={styles.label}>Motion Amplitude (mm) [x, y, z]</label>
                <div style={{ display: 'flex', gap: '4px' }}>
                    {['X', 'Y', 'Z'].map((axis, i) => (
                        <div key={axis} style={{ flex: 1 }}>
                            <input
                                type="number"
                                style={styles.input}
                                value={motionAmplitude[i]}
                                onChange={(e) => updateAmplitude(i, e.target.value)}
                                step={0.5}
                                min={0}
                                placeholder={axis}
                            />
                            <div style={{ ...styles.hint, textAlign: 'center' }}>{axis}</div>
                        </div>
                    ))}
                </div>
            </div>

            <div style={styles.field}>
                <label style={styles.label}>Motion Period (s)</label>
                <input
                    type="number"
                    style={styles.input}
                    value={motionPeriod}
                    onChange={(e) => setMotionPeriod(parseFloat(e.target.value) || 4.0)}
                    step={0.5}
                    min={0.5}
                />
                <div style={styles.hint}>Breathing cycle period</div>
            </div>

            {/* Delivery Parameters */}
            <div style={styles.sectionTitle}>Delivery Parameters</div>

            <div style={styles.field}>
                <label style={styles.label}>Delivery Time per Spot (ms)</label>
                <input
                    type="number"
                    style={styles.input}
                    value={deliveryTimePerSpot}
                    onChange={(e) => setDeliveryTimePerSpot(parseFloat(e.target.value) || 1.0)}
                    step={0.1}
                    min={0.1}
                />
            </div>

            <div style={styles.field}>
                <label style={styles.label}>Number of Fractions</label>
                <input
                    type="number"
                    style={styles.input}
                    value={numFractions}
                    onChange={(e) => setNumFractions(parseInt(e.target.value, 10) || 1)}
                    min={1}
                    max={50}
                />
            </div>

            {/* Submit */}
            <button
                style={{
                    ...styles.button,
                    ...(isSubmitting.current || !planId ? styles.buttonDisabled : {}),
                }}
                onClick={handleSubmit}
                disabled={isSubmitting.current || !planId}
            >
                {isSubmitting.current ? '⏳ Running Simulation...' : '▶ Run Simulation'}
            </button>

            {/* Error */}
            {error && (
                <div style={{ marginTop: '8px', padding: '8px', backgroundColor: '#45263e', borderRadius: '4px', color: '#f38ba8', fontSize: '12px' }}>
                    ⚠ {error}
                </div>
            )}

            {/* Status */}
            {simStatus && (
                <div style={styles.progressContainer}>
                    <span style={{ ...styles.badge, ...(BADGE_COLORS[simStatus] || { backgroundColor: '#45475a', color: '#cdd6f4' }) }}>
                        {simStatus}
                    </span>
                </div>
            )}

            {/* Results */}
            {simResult && (
                <div style={styles.resultCard}>
                    <div style={{ fontSize: '11px', fontWeight: 600, color: '#a6e3a1', marginBottom: '6px', textTransform: 'uppercase' }}>
                        Simulation Results
                    </div>
                    {typeof simResult === 'object' && Object.entries(simResult).map(([key, value]) => {
                        if (typeof value === 'object') return null;
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

SimulationPanel.panelConfig = {
    id: 'radiarch-simulation',
    label: 'Simulation',
    iconName: 'tool-calibration',
};

export default SimulationPanel;
