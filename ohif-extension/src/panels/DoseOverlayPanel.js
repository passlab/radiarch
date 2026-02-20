/**
 * DoseOverlayPanel — Controls for dose visualization on the CT viewport.
 *
 * Provides UI for toggling dose overlay visibility, adjusting opacity,
 * selecting color maps, and setting isodose line thresholds.
 * Actual cornerstone3D rendering integration requires the full OHIF runtime.
 */

import React, { useState } from 'react';

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
    section: {
        marginBottom: '16px',
    },
    sectionTitle: {
        fontSize: '11px',
        fontWeight: 600,
        color: '#a6adc8',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        marginBottom: '8px',
    },
    field: {
        marginBottom: '10px',
    },
    label: {
        display: 'block',
        fontSize: '11px',
        color: '#6c7086',
        marginBottom: '3px',
    },
    toggle: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 10px',
        backgroundColor: '#313244',
        borderRadius: '6px',
        cursor: 'pointer',
        marginBottom: '8px',
    },
    toggleSwitch: (active) => ({
        width: '36px',
        height: '20px',
        borderRadius: '10px',
        backgroundColor: active ? '#89b4fa' : '#45475a',
        position: 'relative',
        transition: 'background-color 0.2s',
    }),
    toggleKnob: (active) => ({
        width: '16px',
        height: '16px',
        borderRadius: '50%',
        backgroundColor: '#cdd6f4',
        position: 'absolute',
        top: '2px',
        left: active ? '18px' : '2px',
        transition: 'left 0.2s',
    }),
    slider: {
        width: '100%',
        marginTop: '4px',
        accentColor: '#89b4fa',
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
    isodoseRow: {
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '4px 0',
        fontSize: '12px',
    },
    checkbox: {
        accentColor: '#89b4fa',
    },
    isodoseColor: (color) => ({
        width: '12px',
        height: '12px',
        borderRadius: '2px',
        backgroundColor: color,
    }),
    statusCard: {
        padding: '10px',
        backgroundColor: '#313244',
        borderRadius: '6px',
        marginBottom: '12px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
    },
    statusDot: (available) => ({
        width: '8px',
        height: '8px',
        borderRadius: '50%',
        backgroundColor: available ? '#a6e3a1' : '#f38ba8',
    }),
    loadButton: {
        width: '100%',
        padding: '8px',
        backgroundColor: '#89b4fa',
        color: '#1e1e2e',
        border: 'none',
        borderRadius: '6px',
        fontSize: '13px',
        fontWeight: 600,
        cursor: 'pointer',
        marginTop: '8px',
    },
    loadButtonDisabled: {
        backgroundColor: '#45475a',
        color: '#6c7086',
        cursor: 'not-allowed',
    },
};

const ISODOSE_LEVELS = [
    { level: 107, color: '#f38ba8', label: '107% (Hot spot)' },
    { level: 100, color: '#fab387', label: '100% (Prescription)' },
    { level: 95, color: '#f9e2af', label: '95%' },
    { level: 80, color: '#a6e3a1', label: '80%' },
    { level: 50, color: '#89b4fa', label: '50%' },
    { level: 30, color: '#cba6f7', label: '30%' },
];

const COLOR_MAPS = [
    { value: 'jet', label: 'Jet' },
    { value: 'hot', label: 'Hot' },
    { value: 'rainbow', label: 'Rainbow' },
    { value: 'turbo', label: 'Turbo' },
    { value: 'viridis', label: 'Viridis' },
];

function DoseOverlayPanel({ commandsManager }) {
    const [doseVisible, setDoseVisible] = useState(false);
    const [opacity, setOpacity] = useState(50);
    const [colorMap, setColorMap] = useState('jet');
    const [isodoseLevels, setIsodoseLevels] = useState(
        ISODOSE_LEVELS.reduce((acc, lvl) => {
            acc[lvl.level] = lvl.level >= 80; // Enable ≥80% by default
            return acc;
        }, {})
    );
    const [doseLoaded, setDoseLoaded] = useState(false);
    const [loading, setLoading] = useState(false);
    const [artifactId, setArtifactId] = useState('');

    const toggleIsodose = (level) => {
        setIsodoseLevels((prev) => ({ ...prev, [level]: !prev[level] }));
    };

    const handleLoadDose = async () => {
        if (!artifactId || loading) return;
        setLoading(true);
        try {
            await commandsManager.runCommand('radiarch.loadDose', { artifactId });
            setDoseLoaded(true);
            setDoseVisible(true);
        } catch (err) {
            console.error('Failed to load dose:', err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={styles.panel}>
            <h3 style={styles.header}>🎨 Dose Overlay</h3>

            {/* RTDOSE Status */}
            <div style={styles.statusCard}>
                <div style={styles.statusDot(doseLoaded)} />
                <span style={{ fontSize: '12px', color: '#a6adc8' }}>
                    {doseLoaded ? 'RTDOSE loaded' : 'No dose data loaded'}
                </span>
            </div>

            {/* Artifact ID + Load */}
            <div style={styles.section}>
                <div style={styles.sectionTitle}>Load RTDOSE</div>
                <input
                    type="text"
                    placeholder="Artifact ID..."
                    value={artifactId}
                    onChange={(e) => setArtifactId(e.target.value)}
                    style={{
                        width: '100%',
                        padding: '6px 8px',
                        backgroundColor: '#313244',
                        border: '1px solid #45475a',
                        borderRadius: '4px',
                        color: '#cdd6f4',
                        fontSize: '12px',
                        outline: 'none',
                        boxSizing: 'border-box',
                    }}
                />
                <button
                    style={{
                        ...styles.loadButton,
                        ...(loading || !artifactId ? styles.loadButtonDisabled : {}),
                    }}
                    onClick={handleLoadDose}
                    disabled={loading || !artifactId}
                >
                    {loading ? '⏳ Loading...' : '📥 Load Dose'}
                </button>
            </div>

            {/* Visibility Toggle */}
            <div style={styles.toggle} onClick={() => setDoseVisible(!doseVisible)}>
                <span style={{ fontWeight: 500 }}>Dose Display</span>
                <div style={styles.toggleSwitch(doseVisible)}>
                    <div style={styles.toggleKnob(doseVisible)} />
                </div>
            </div>

            {/* Opacity */}
            <div style={styles.section}>
                <div style={styles.sectionTitle}>Opacity</div>
                <input
                    type="range"
                    min={0}
                    max={100}
                    value={opacity}
                    onChange={(e) => setOpacity(parseInt(e.target.value, 10))}
                    style={styles.slider}
                />
                <div style={{ fontSize: '11px', color: '#6c7086', textAlign: 'center' }}>
                    {opacity}%
                </div>
            </div>

            {/* Color Map */}
            <div style={styles.section}>
                <div style={styles.sectionTitle}>Color Map</div>
                <select
                    style={styles.select}
                    value={colorMap}
                    onChange={(e) => setColorMap(e.target.value)}
                >
                    {COLOR_MAPS.map((cm) => (
                        <option key={cm.value} value={cm.value}>{cm.label}</option>
                    ))}
                </select>
            </div>

            {/* Isodose Lines */}
            <div style={styles.section}>
                <div style={styles.sectionTitle}>Isodose Lines</div>
                {ISODOSE_LEVELS.map((iso) => (
                    <div key={iso.level} style={styles.isodoseRow}>
                        <input
                            type="checkbox"
                            checked={!!isodoseLevels[iso.level]}
                            onChange={() => toggleIsodose(iso.level)}
                            style={styles.checkbox}
                        />
                        <div style={styles.isodoseColor(iso.color)} />
                        <span style={{ color: '#cdd6f4' }}>{iso.label}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}

DoseOverlayPanel.panelConfig = {
    id: 'radiarch-dose-overlay',
    label: 'Dose Overlay',
    iconName: 'viewport-window-level',
};

export default DoseOverlayPanel;
