/**
 * DVHPanel — Interactive Dose-Volume Histogram chart.
 *
 * Uses Chart.js to render DVH curves from plan QA summary data.
 * Auto-populates when a plan completes; shows empty state otherwise.
 */

import React, { useState, useEffect, useMemo, useRef } from 'react';

// We use a lightweight inline SVG chart to avoid hard Chart.js dependency.
// If chart.js + react-chartjs-2 are available, a richer version can be swapped in.

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
    emptyState: {
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '200px',
        color: '#6c7086',
        fontSize: '13px',
        textAlign: 'center',
    },
    chartContainer: {
        backgroundColor: '#313244',
        borderRadius: '8px',
        padding: '12px',
        marginBottom: '12px',
    },
    statsGrid: {
        display: 'grid',
        gridTemplateColumns: '1fr 1fr 1fr',
        gap: '8px',
        marginTop: '12px',
    },
    statCard: {
        backgroundColor: '#313244',
        borderRadius: '6px',
        padding: '10px',
        textAlign: 'center',
    },
    statValue: {
        fontSize: '18px',
        fontWeight: 700,
        color: '#89b4fa',
    },
    statLabel: {
        fontSize: '10px',
        color: '#6c7086',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        marginTop: '2px',
    },
    legend: {
        display: 'flex',
        gap: '12px',
        marginTop: '8px',
        fontSize: '11px',
        color: '#a6adc8',
        flexWrap: 'wrap',
    },
    legendDot: (color) => ({
        display: 'inline-block',
        width: '8px',
        height: '8px',
        borderRadius: '50%',
        backgroundColor: color,
        marginRight: '4px',
        verticalAlign: 'middle',
    }),
    refreshButton: {
        padding: '6px 14px',
        backgroundColor: '#45475a',
        color: '#cdd6f4',
        border: 'none',
        borderRadius: '4px',
        fontSize: '12px',
        cursor: 'pointer',
        marginTop: '8px',
    },
};

const COLORS = ['#89b4fa', '#a6e3a1', '#f9e2af', '#f38ba8', '#cba6f7', '#fab387'];

// ---------------------------------------------------------------------------
// SVG Line Chart (self-contained, no Chart.js dependency)
// ---------------------------------------------------------------------------

function SVGLineChart({ data, width = 320, height = 200 }) {
    if (!data || data.length === 0) return null;

    const margin = { top: 10, right: 10, bottom: 30, left: 40 };
    const chartW = width - margin.left - margin.right;
    const chartH = height - margin.top - margin.bottom;

    // Normalize field names: accept both doseGy/volumePct and dose/volume
    const normalizedData = data.map((d) => ({
        ...d,
        doseGy: d.doseGy || d.dose || [],
        volumePct: d.volumePct || d.volume || [],
    }));

    const allDoses = normalizedData.flatMap((d) => d.doseGy);
    const maxDose = Math.max(...allDoses, 1);

    const scaleX = (v) => margin.left + (v / maxDose) * chartW;
    const scaleY = (v) => margin.top + chartH - (v / 100) * chartH;

    // Grid lines
    const gridLinesY = [0, 25, 50, 75, 100];
    const gridLinesX = Array.from({ length: 5 }, (_, i) => (maxDose * (i + 1)) / 5);

    return (
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
            {/* Grid */}
            {gridLinesY.map((v) => (
                <g key={`gy-${v}`}>
                    <line
                        x1={margin.left} y1={scaleY(v)}
                        x2={width - margin.right} y2={scaleY(v)}
                        stroke="#45475a" strokeWidth={0.5}
                    />
                    <text x={margin.left - 4} y={scaleY(v) + 3} fill="#6c7086" fontSize="9" textAnchor="end">
                        {v}%
                    </text>
                </g>
            ))}
            {gridLinesX.map((v) => (
                <g key={`gx-${v}`}>
                    <line
                        x1={scaleX(v)} y1={margin.top}
                        x2={scaleX(v)} y2={margin.top + chartH}
                        stroke="#45475a" strokeWidth={0.5}
                    />
                    <text x={scaleX(v)} y={height - 5} fill="#6c7086" fontSize="9" textAnchor="middle">
                        {v.toFixed(1)}
                    </text>
                </g>
            ))}

            {/* Axes labels */}
            <text x={width / 2} y={height - 1} fill="#a6adc8" fontSize="10" textAnchor="middle">
                Dose (Gy)
            </text>
            <text
                x={8} y={height / 2}
                fill="#a6adc8" fontSize="10" textAnchor="middle"
                transform={`rotate(-90, 8, ${height / 2})`}
            >
                Volume (%)
            </text>

            {/* DVH curves */}
            {normalizedData.map((curve, ci) => {
                const doses = curve.doseGy;
                const vols = curve.volumePct;
                if (doses.length < 2) return null;

                const pathData = doses.map((d, i) =>
                    `${i === 0 ? 'M' : 'L'} ${scaleX(d)} ${scaleY(vols[i] || 0)}`
                ).join(' ');

                return (
                    <path
                        key={ci}
                        d={pathData}
                        fill="none"
                        stroke={COLORS[ci % COLORS.length]}
                        strokeWidth={2}
                        strokeLinejoin="round"
                    />
                );
            })}
        </svg>
    );
}

// ---------------------------------------------------------------------------
// Main Panel
// ---------------------------------------------------------------------------

function DVHPanel({ commandsManager, servicesManager }) {
    const [dvhData, setDvhData] = useState(null);
    const [stats, setStats] = useState(null);
    const [planId, setPlanId] = useState('');

    const loadDvh = async (id) => {
        if (!id) return;
        try {
            const planResult = await commandsManager.runCommand('radiarch.loadPlanResult', { planId: id });
            const qa = planResult?.qa_summary;
            if (qa?.dvh) {
                // DVH might be a single object or array
                const dvhArray = Array.isArray(qa.dvh) ? qa.dvh : [qa.dvh];
                // Accept both doseGy/volumePct and dose/volume field names
                setDvhData(dvhArray.filter((d) => (d.doseGy || d.dose) && (d.volumePct || d.volume)));
                setStats({
                    minDoseGy: qa.dvh.minDoseGy ?? qa.dvh?.min_dose_gy ?? qa.minDoseGy,
                    maxDoseGy: qa.dvh.maxDoseGy ?? qa.dvh?.max_dose_gy,
                    meanDoseGy: qa.dvh.meanDoseGy ?? qa.dvh?.mean_dose_gy,
                    roiName: qa.dvh.roiName ?? qa.dvh?.roi_name ?? 'Target',
                });
            }
        } catch (err) {
            console.error('Failed to load DVH:', err);
        }
    };

    // Listen for plan completion events (simplified: manual refresh)
    return (
        <div style={styles.panel}>
            <h3 style={styles.header}>📊 Dose-Volume Histogram</h3>

            {/* Manual plan ID input for loading DVH */}
            <div style={{ marginBottom: '12px' }}>
                <div style={{ display: 'flex', gap: '4px' }}>
                    <input
                        type="text"
                        placeholder="Plan ID..."
                        value={planId}
                        onChange={(e) => setPlanId(e.target.value)}
                        style={{
                            flex: 1,
                            padding: '6px 8px',
                            backgroundColor: '#313244',
                            border: '1px solid #45475a',
                            borderRadius: '4px',
                            color: '#cdd6f4',
                            fontSize: '12px',
                            outline: 'none',
                        }}
                    />
                    <button
                        style={styles.refreshButton}
                        onClick={() => loadDvh(planId)}
                    >
                        Load
                    </button>
                </div>
            </div>

            {/* Chart or empty state */}
            {dvhData && dvhData.length > 0 ? (
                <>
                    <div style={styles.chartContainer}>
                        <SVGLineChart data={dvhData} width={320} height={200} />
                        <div style={styles.legend}>
                            {dvhData.map((curve, i) => (
                                <span key={i}>
                                    <span style={styles.legendDot(COLORS[i % COLORS.length])} />
                                    {curve.roiName || `Structure ${i + 1}`}
                                </span>
                            ))}
                        </div>
                    </div>

                    {/* Stats cards */}
                    {stats && (
                        <div style={styles.statsGrid}>
                            {stats.minDoseGy != null && (
                                <div style={styles.statCard}>
                                    <div style={styles.statValue}>{Number(stats.minDoseGy).toFixed(2)}</div>
                                    <div style={styles.statLabel}>Min Dose (Gy)</div>
                                </div>
                            )}
                            {stats.maxDoseGy != null && (
                                <div style={styles.statCard}>
                                    <div style={{ ...styles.statValue, color: '#f38ba8' }}>
                                        {Number(stats.maxDoseGy).toFixed(2)}
                                    </div>
                                    <div style={styles.statLabel}>Max Dose (Gy)</div>
                                </div>
                            )}
                            {stats.meanDoseGy != null && (
                                <div style={styles.statCard}>
                                    <div style={{ ...styles.statValue, color: '#a6e3a1' }}>
                                        {Number(stats.meanDoseGy).toFixed(2)}
                                    </div>
                                    <div style={styles.statLabel}>Mean Dose (Gy)</div>
                                </div>
                            )}
                        </div>
                    )}
                </>
            ) : (
                <div style={styles.emptyState}>
                    <div style={{ fontSize: '32px', marginBottom: '8px' }}>📈</div>
                    <div>No DVH data available</div>
                    <div style={{ fontSize: '11px', marginTop: '4px' }}>
                        Submit a plan to view dose-volume histogram data
                    </div>
                </div>
            )}
        </div>
    );
}

DVHPanel.panelConfig = {
    id: 'radiarch-dvh',
    label: 'DVH',
    iconName: 'chart',
};

export default DVHPanel;
