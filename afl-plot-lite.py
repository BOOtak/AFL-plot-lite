#!/usr/bin/env python3
"""
afl-plot.py - Lightweight replacement for afl-plot (no gnuplot, no GUI)
Automatically downsamples data to keep HTML size small.
Edge coverage is plotted as (edges - initial_edges) so the curve starts at 0,
with y-axis labels and tooltips showing the actual edge count.
Usage: ./afl-plot.py [--debug] [--max-points N] <input_dir1> [input_dir2 ...] <output_dir>
"""

import sys
import os
import argparse
import time
import json
import math
from pathlib import Path
from collections import defaultdict

# ---- CLI parsing ----
def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate interactive HTML plots from afl-fuzz plot_data",
        epilog="The output is a self-contained HTML file with Chart.js charts."
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Print debug information about data parsing"
    )
    parser.add_argument(
        "--max-points", type=int, default=2000,
        help="Maximum number of data points per dataset (default: 2000)"
    )
    parser.add_argument(
        "directories", nargs="+",
        help="Input directories (one or more) and output directory as the last argument"
    )
    args = parser.parse_args()
    if len(args.directories) < 2:
        parser.error("Need at least one input directory and one output directory.")
    output_dir = args.directories[-1]
    input_dirs = args.directories[:-1]
    return args.debug, args.max_points, input_dirs, output_dir

# ---- Validation ----
def validate_input_dir(d, is_single, debug=False):
    plot_file = Path(d) / "plot_data"
    if not plot_file.is_file():
        if (Path(d) / "default" / "plot_data").is_file():
            msg = f"Did you mean {d}/default? (missing plot_data)"
        else:
            msg = "missing plot_data"
        if is_single:
            sys.exit(f"[-] Error: input directory '{d}' is not valid ({msg})")
        else:
            print(f"[!] Warning: skipping '{d}' ({msg})", file=sys.stderr)
            return None

    with open(plot_file) as f:
        lines = f.readlines()
        data_lines = [l for l in lines if not l.startswith('#') and l.strip()]
        if len(data_lines) < 2:
            if is_single:
                sys.exit(f"[-] Error: '{plot_file}' has too little data (need at least 2 data lines)")
            else:
                print(f"[!] Warning: skipping '{d}' (only {len(data_lines)} data lines)", file=sys.stderr)
                return None
    if debug:
        print(f"[DEBUG] {d}/plot_data: {len(data_lines)} data lines found.", file=sys.stderr)
    return d

# ---- Downsampling ----
def downsample(x, y, max_points):
    """Uniformly downsample to at most max_points while preserving shape."""
    n = len(x)
    if n <= max_points:
        return x, y
    step = (n - 1) / (max_points - 1)
    indices = [int(round(i * step)) for i in range(max_points)]
    return [x[i] for i in indices], [y[i] for i in indices]

# ---- Data reading ----
def read_plot_data(d, max_points, debug=False):
    data = defaultdict(list)
    data_file = Path(d) / "plot_data"
    with open(data_file) as f:
        lines = f.readlines()
    data_lines = [l for l in lines if not l.startswith('#') and l.strip()]
    if debug:
        print(f"[DEBUG] Reading {len(data_lines)} lines from {data_file}", file=sys.stderr)

    parsed_count = 0
    for line in data_lines:
        parts = line.strip().split()
        if len(parts) < 13:
            continue
        try:
            vals = []
            for i in range(13):
                token = parts[i].strip().replace(',', '').replace('%', '')
                vals.append(float(token))
        except ValueError:
            continue
        data['time'].append(vals[0])
        data['cycles'].append(vals[1])
        data['cur_item'].append(vals[2])
        data['corpus'].append(vals[3])
        data['pending'].append(vals[4])
        data['pending_favs'].append(vals[5])
        data['map_size'].append(vals[6])
        data['crashes'].append(vals[7])
        data['hangs'].append(vals[8])
        data['max_depth'].append(vals[9])
        data['execs'].append(vals[10])
        data['total_execs'].append(vals[11])
        data['edges'].append(vals[12])
        parsed_count += 1

    if debug:
        print(f"[DEBUG] Parsed {parsed_count} valid data points from {d}", file=sys.stderr)

    if data['time']:
        t0 = data['time'][0]
        time_rel = [t - t0 for t in data['time']]
        n = len(time_rel)
        if n > max_points:
            step = (n - 1) / (max_points - 1)
            indices = [int(round(i * step)) for i in range(max_points)]
            data['time_rel'] = [time_rel[i] for i in indices]
            data['cycles'] = [data['cycles'][i] for i in indices]
            data['cur_item'] = [data['cur_item'][i] for i in indices]
            data['corpus'] = [data['corpus'][i] for i in indices]
            data['pending'] = [data['pending'][i] for i in indices]
            data['pending_favs'] = [data['pending_favs'][i] for i in indices]
            data['crashes'] = [data['crashes'][i] for i in indices]
            data['hangs'] = [data['hangs'][i] for i in indices]
            data['max_depth'] = [data['max_depth'][i] for i in indices]
            data['execs'] = [data['execs'][i] for i in indices]
            data['edges'] = [data['edges'][i] for i in indices]
            if debug:
                print(f"[DEBUG] Downsampled to {len(data['time_rel'])} points", file=sys.stderr)
        else:
            data['time_rel'] = time_rel
        if debug:
            print(f"[DEBUG] Time range: {data['time_rel'][0]:.0f} to {data['time_rel'][-1]:.0f} seconds", file=sys.stderr)
            print(f"[DEBUG] First few execs/sec: {data['execs'][:3]}", file=sys.stderr)
            print(f"[DEBUG] First few edges: {data['edges'][:3]}", file=sys.stderr)
    else:
        data['time_rel'] = []
        if debug:
            print(f"[DEBUG] No data parsed!", file=sys.stderr)

    return data

# ---- Banner ----
def get_banner(d):
    stats = Path(d) / "fuzzer_stats"
    if stats.is_file():
        with open(stats) as f:
            for line in f:
                if line.startswith('afl_banner'):
                    banner = line.split(':', 1)[1].strip()
                    return banner
    return os.path.basename(d)

# ---- Colors ----
COLORS = ["#0090ff", "#c00080", "#c000f0", "#00c020", "#f07000",
          "#e0c000", "#8000ff", "#ff0040", "#00bfbf", "#808000"]

def get_color(idx):
    return COLORS[(idx - 1) % len(COLORS)]

# ---- HTML generation ----
def generate_html(input_dirs, data_dict, banners, output_dir, max_points, debug=False):
    js_data = {
        'high_freq': [],
        'low_freq': [],
        'exec_speed': [],
        'edges': []
    }

    single_dir = len(input_dirs) == 1
    initial_edge = None
    if single_dir:
        d = input_dirs[0]
        if data_dict[d]['edges']:
            initial_edge = data_dict[d]['edges'][0]
        else:
            initial_edge = 0

    for idx, d in enumerate(input_dirs):
        data = data_dict[d]
        if not data['time_rel']:
            print(f"[!] Warning: No data for {d}, skipping", file=sys.stderr)
            continue
        color = get_color(idx + 1)
        label = banners[d]

        # ---- High-frequency ----
        js_data['high_freq'].append({
            'label': f'{label} corpus',
            'data': [{'x': t, 'y': c} for t, c in zip(data['time_rel'], data['corpus'])],
            'borderColor': color,
            'backgroundColor': color + '33',
            'fill': True,
            'tension': 0.2,
            'pointRadius': 0,
        })
        js_data['high_freq'].append({
            'label': f'{label} current',
            'data': [{'x': t, 'y': c} for t, c in zip(data['time_rel'], data['cur_item'])],
            'borderColor': '#f0f0f0',
            'backgroundColor': '#f0f0f066',
            'fill': True,
            'tension': 0.2,
            'pointRadius': 0,
        })
        js_data['high_freq'].append({
            'label': f'{label} pending',
            'data': [{'x': t, 'y': c} for t, c in zip(data['time_rel'], data['pending'])],
            'borderColor': color,
            'borderDash': [5, 5],
            'fill': False,
            'tension': 0.2,
            'pointRadius': 0,
        })
        js_data['high_freq'].append({
            'label': f'{label} favs',
            'data': [{'x': t, 'y': c} for t, c in zip(data['time_rel'], data['pending_favs'])],
            'borderColor': '#c00080',
            'fill': False,
            'tension': 0.2,
            'pointRadius': 0,
        })
        js_data['high_freq'].append({
            'label': f'{label} cycles',
            'data': [{'x': t, 'y': c} for t, c in zip(data['time_rel'], data['cycles'])],
            'borderColor': '#c000f0',
            'fill': False,
            'tension': 0.2,
            'pointRadius': 0,
        })

        # ---- Low-frequency ----
        js_data['low_freq'].append({
            'label': f'{label} crashes',
            'data': [{'x': t, 'y': c} for t, c in zip(data['time_rel'], data['crashes'])],
            'borderColor': color,
            'backgroundColor': color + '33',
            'fill': True,
            'tension': 0.2,
            'pointRadius': 0,
        })
        js_data['low_freq'].append({
            'label': f'{label} hangs',
            'data': [{'x': t, 'y': c} for t, c in zip(data['time_rel'], data['hangs'])],
            'borderColor': '#c000f0',
            'borderDash': [5, 5],
            'fill': False,
            'tension': 0.2,
            'pointRadius': 0,
        })
        js_data['low_freq'].append({
            'label': f'{label} depth',
            'data': [{'x': t, 'y': c} for t, c in zip(data['time_rel'], data['max_depth'])],
            'borderColor': '#0090ff',
            'fill': False,
            'tension': 0.2,
            'pointRadius': 0,
        })

        # ---- Execution speed ----
        js_data['exec_speed'].append({
            'label': f'{label} execs/s',
            'data': [{'x': t, 'y': c} for t, c in zip(data['time_rel'], data['execs'])],
            'borderColor': color,
            'backgroundColor': color + '33',
            'fill': True,
            'tension': 0.2,
            'pointRadius': 0,
        })

        # ---- Edge coverage ----
        if single_dir and initial_edge is not None:
            # Offset: edges - initial_edges
            offset_edges = [e - initial_edge for e in data['edges']]
        else:
            # Absolute edges (no offset)
            offset_edges = data['edges']

        js_data['edges'].append({
            'label': f'{label} edges',
            'data': [{'x': t, 'y': e} for t, e in zip(data['time_rel'], offset_edges)],
            'borderColor': color,
            'fill': False,
            'tension': 0.2,
            'pointRadius': 0,
        })

    if debug:
        total_points = sum(len(ds['data']) for ds in js_data['high_freq']) + \
                       sum(len(ds['data']) for ds in js_data['low_freq']) + \
                       sum(len(ds['data']) for ds in js_data['exec_speed']) + \
                       sum(len(ds['data']) for ds in js_data['edges'])
        print(f"[DEBUG] Generated datasets: high_freq={len(js_data['high_freq'])}, "
              f"low_freq={len(js_data['low_freq'])}, "
              f"exec_speed={len(js_data['exec_speed'])}, "
              f"edges={len(js_data['edges'])}", file=sys.stderr)
        print(f"[DEBUG] Total data points in HTML: {total_points}", file=sys.stderr)

    chart_data_json = json.dumps(js_data, indent=2)

    banner_rows = ""
    for d in input_dirs:
        color = get_color(input_dirs.index(d) + 1)
        banner_rows += f"<tr><td><span class='color-dot' style='background:{color};'></span>{banners[d]}</td><td>{d}</td></tr>\n"

    edge_initial_value = initial_edge if single_dir else None

    html_template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AFL++ Plot Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        body {{ font-family: 'Trebuchet MS', 'Tahoma', 'Arial', 'Helvetica'; margin: 20px; }}
        .info {{ margin-bottom: 20px; }}
        .chart-container {{ width: 1000px; margin-bottom: 40px; }}
        .chart-container canvas {{ width: 100% !important; height: 100% !important; }}
        .legend {{ margin: 10px 0; }}
        .legend-item {{ display: inline-block; margin-right: 20px; }}
        .color-dot {{ display: inline-block; width: 12px; height: 12px; border-radius: 2px; margin-right: 5px; }}
        .banner-table {{ border-collapse: collapse; margin-bottom: 20px; }}
        .banner-table td {{ padding: 4px 10px; border: 1px solid #ddd; }}
    </style>
</head>
<body>
    <h1>AFL++ Progress Dashboard</h1>
    <div class="info">
        <p><strong>Generated on:</strong> {generated}</p>
        <p><strong>Instances:</strong> {num_instances}</p>
        <table class="banner-table">
            <tr><th>Banner</th><th>Directory</th></tr>
            {banner_rows}
        </table>
    </div>

    <div class="chart-container" style="height:300px;">
        <h2>High-frequency trends</h2>
        <canvas id="highFreqChart"></canvas>
    </div>
    <div class="chart-container" style="height:200px;">
        <h2>Low-frequency trends (crashes, hangs, depth)</h2>
        <canvas id="lowFreqChart"></canvas>
    </div>
    <div class="chart-container" style="height:200px;">
        <h2>Execution speed</h2>
        <canvas id="execSpeedChart"></canvas>
    </div>
    <div class="chart-container" style="height:300px;">
        <h2>Edge coverage</h2>
        <canvas id="edgesChart"></canvas>
    </div>

    <script>
        const chartData = {chart_data};
        const edgeInitial = {edge_initial};

        function createChart(id, datasets, yLabel, tickCallback, tooltipCallback) {{
            const ctx = document.getElementById(id).getContext('2d');
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    datasets: datasets
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        tooltip: {{
                            callbacks: {{
                                label: tooltipCallback
                            }}
                        }},
                        legend: {{
                            position: 'bottom',
                            labels: {{
                                boxWidth: 12,
                                padding: 10,
                                font: {{ size: 11 }}
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            type: 'linear',
                            title: {{
                                display: true,
                                text: 'Relative time (seconds)',
                                font: {{ size: 12 }}
                            }},
                            grid: {{
                                color: '#e0e0e0'
                            }}
                        }},
                        y: {{
                            title: {{
                                display: true,
                                text: yLabel,
                                font: {{ size: 12 }}
                            }},
                            grid: {{
                                color: '#e0e0e0'
                            }},
                            beginAtZero: true,
                            ticks: {{
                                callback: tickCallback
                            }}
                        }}
                    }},
                    elements: {{
                        point: {{
                            radius: 0
                        }},
                        line: {{
                            tension: 0.2,
                            borderWidth: 2
                        }}
                    }}
                }}
            }});
        }}

        // Default tooltip: just show the value
        function defaultTooltip(context) {{
            let label = context.dataset.label || '';
            let value = context.parsed.y;
            return label + ': ' + value.toFixed(0);
        }}

        // Custom tick callback for edge chart (adds initial edge)
        function edgeTick(value) {{
            if (edgeInitial !== null && edgeInitial !== undefined) {{
                return (value + edgeInitial).toFixed(0);
            }}
            return value.toFixed(0);
        }}

        // Custom tooltip for edge chart (adds initial edge)
        function edgeTooltip(context) {{
            let label = context.dataset.label || '';
            let value = context.parsed.y;
            if (edgeInitial !== null && edgeInitial !== undefined) {{
                value += edgeInitial;
            }}
            return label + ': ' + value.toFixed(0);
        }}

        createChart('highFreqChart', chartData.high_freq, 'Count', function(v){{ return v.toFixed(0); }}, defaultTooltip);
        createChart('lowFreqChart', chartData.low_freq, 'Count', function(v){{ return v.toFixed(0); }}, defaultTooltip);
        createChart('execSpeedChart', chartData.exec_speed, 'Execs/sec', function(v){{ return v.toFixed(1); }}, defaultTooltip);
        createChart('edgesChart', chartData.edges, 'Edges', edgeTick, edgeTooltip);
    </script>
</body>
</html>
"""

    html_content = html_template.format(
        generated=time.strftime("%Y-%m-%d %H:%M:%S"),
        num_instances=len(input_dirs),
        banner_rows=banner_rows,
        chart_data=chart_data_json,
        edge_initial=json.dumps(edge_initial_value) if edge_initial_value is not None else 'null'
    )

    output_file = Path(output_dir) / "index.html"
    with open(output_file, "w") as f:
        f.write(html_content)

    file_size = os.path.getsize(output_file) / (1024 * 1024)
    print(f"[+] Dashboard generated: {output_file} ({file_size:.2f} MB)")
    print("[*] Open this file in your browser to view the plots.")

# ---- Main ----
def main():
    debug, max_points, input_dirs, output_dir = parse_args()
    os.makedirs(output_dir, exist_ok=True)

    valid_dirs = []
    is_single = len(input_dirs) == 1
    for d in input_dirs:
        v = validate_input_dir(d, is_single, debug)
        if v:
            valid_dirs.append(v)

    if not valid_dirs:
        sys.exit("[-] Error: no valid input directories with plot_data.")

    data_dict = {}
    banners = {}
    for d in valid_dirs:
        data_dict[d] = read_plot_data(d, max_points, debug)
        banners[d] = get_banner(d)

    generate_html(valid_dirs, data_dict, banners, output_dir, max_points, debug)

if __name__ == "__main__":
    main()
