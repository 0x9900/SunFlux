# SunFlux

SunFlux is a collection of Python tools for monitoring solar activity, space weather, and radio propagation conditions for amateur radio operators.

The tools retrieve and process space-weather data, generate graphs, and provide information useful for understanding HF propagation conditions.

## Features

- **Solar activity:** Sunspot numbers, historical data, and predictions.
- **Space weather:** Solar wind, X-ray flux, proton flux, and geomagnetic indices.
- **Radio propagation:** Ionospheric and propagation-related graphs and forecasts.
- **DXCC statistics:** Reports based on amateur radio DX cluster data.

## Installation

SunFlux requires Python 3.12 or later.

Clone the repository and install the project and its dependencies:

```bash
git clone https://github.com/0x9900/sunflux.git
cd sunflux
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuration

SunFlux uses a YAML configuration file named `sunflux.yaml`. The file defines settings such as output directories, cache locations, cache lifetimes, and database paths.

Review the supplied `sunflux.yaml` and adjust the paths and settings to match your environment before running the tools. The configuration file must be available in one of the locations searched by SunFlux.

## Usage

Installation provides command-line tools for the individual tasks, including `fluxgraph`, `ssngraph`, `solarwind`, `xray_flux`, `pkiforecast`, and `showdxcc`.

Run a tool with `--help` to check its available options.

## Online resources

- [SunFlux project website](https://bsdworld.org/)
- [SunFlux Telegram bot](https://t.me/SunFluxBot)

## License

SunFlux is distributed under the BSD 2-Clause License. See [LICENSE](LICENSE) for details.
