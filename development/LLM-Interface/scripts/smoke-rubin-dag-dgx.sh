#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/dgx-env.sh"

rubin_data="${CGSIM_SOURCE_ROOT}/rubin-data"
smoke_dir="$(mktemp -d /tmp/cgsim-rubin-smoke.XXXXXX)"
trap 'rm -rf "${smoke_dir}"' EXIT

python3 "${rubin_data}/generate_campaign.py" --out-dir "${smoke_dir}"

python3 -c '
import json, sys
source, target, artifacts = sys.argv[1:]
with open(source) as stream:
    config = json.load(stream)
custom = config["Custom_Parameters"]
custom["qgraph_file"] = artifacts + "/qgraph_export.json"
custom["clustering_file"] = artifacts + "/clustering.json"
custom["campaign_file"] = artifacts + "/campaign.json"
custom["resources_file"] = artifacts + "/resources.json"
config["Sites_Information"] = artifacts + "/site_info.json"
custom["output_file"] = artifacts + "/rubin_dag_output.db"
with open(target, "w") as stream:
    json.dump(config, stream, indent=2)
' "${rubin_data}/rubin_dag_config.json" "${smoke_dir}/rubin_dag_config.json" "${smoke_dir}"

cg-sim -c "${smoke_dir}/rubin_dag_config.json"
python3 "${rubin_data}/verify_dag_order.py" \
  "${smoke_dir}/rubin_dag_output.db" \
  --qgraph "${smoke_dir}/qgraph_export.json" \
  --clustering "${smoke_dir}/clustering.json"
