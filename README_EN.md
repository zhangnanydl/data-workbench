# Data Workbench

<p align="center">
  <img src="frontend/src/assets/data-workbench-logo.png" alt="Data Workbench logo" width="112" />
</p>

<p align="center">
  A local-first, visual and plugin-driven data pipeline for CTF, security analysis, and everyday data preparation.
</p>

> This is an early public preview. Core reading, transformation, preview, full-run, and export paths are functional, while the plugin API and project format may still change before `1.0.0`.

[简体中文](README.md) · [Architecture](docs/ARCHITECTURE.md) · [Plugin development](docs/PLUGIN_DEVELOPMENT.md) · [Contributing](CONTRIBUTING.md)

## Screenshots

### Visual pipeline and live data preview

![Data Workbench visual pipeline](docs/screenshots/workbench-overview.png)

### Full-run progress and animated data flow

![Data Workbench processing progress](docs/screenshots/processing-progress.png)

## Highlights

- Compose input, transform, and output nodes on a visual DAG canvas.
- Configure nodes with generated forms and automatically discovered upstream columns.
- Compare a node's direct input with its processed output; paginate, select columns, and copy table data.
- Read Excel/CSV, TXT, security logs, JSON/JSONL, Windows EVTX, SQLite, MySQL, and PCAP/PCAPNG.
- Use 30 built-in transforms, including filters, mapping, splitting, aggregation, masking, Base/URL/Hex codecs, AES, XOR/Caesar analysis, TCP reassembly, protocol extraction, and flag scanning.
- Export full results to Excel/CSV/TXT, JSON/JSONL, SQLite, MySQL, or a complete PCAP index export.
- Keep large previews responsive with sampling while formal runs continue to process the complete source.
- Show an obvious bottom-of-canvas activity bar for preview loading and formal runs, including percentage, rows, node position, and elapsed time.
- Add external Python plugins without modifying the execution engine or frontend.

The project currently ships **44 built-in nodes**: 9 inputs, 30 transforms, and 5 outputs.

## Data correctness model

Preview pagination never defines the processing boundary. Small inputs are fully processed before their result is paginated. Sources around 32 MiB or 250,000 estimated rows switch to an explicitly labelled 50,000-row fast preview. A formal run reads the complete CSV, SQLite, or MySQL source in batches and reports progress. PCAP files use an on-disk SQLite index for paging and complete export.

## Run from source on Windows

Requirements: Python 3.11+, Node.js 20+, npm, and Microsoft Edge WebView2 Runtime.

```powershell
git clone https://github.com/zhangnanydl/data-workbench.git
cd data-workbench

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[test,build]"

cd frontend
npm ci
npm run build
cd ..

python app.py
```

To build the portable Windows distribution:

```powershell
.\build-exe.ps1
```

Distribute the complete `dist/数据工坊/` directory, not the executable alone.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q

cd frontend
npm run build
npm run test:sites
```

## Security and privacy

Projects are stored locally by default, with optional project-metadata storage in a user-controlled MySQL database. Database credentials and local project files must not be committed. External plugins execute as local Python code with the application's permissions; install only trusted plugins.

Use this project only for authorized CTF, training, forensic, and data-processing work. Please report vulnerabilities according to [SECURITY.md](SECURITY.md).

## License

Licensed under the [Apache License 2.0](LICENSE).
