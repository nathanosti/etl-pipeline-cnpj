#!/usr/bin/env bash
# Cria a conta de serviço que o painel no Streamlit Community Cloud usa para ler a gold no BigQuery.
#
# Permissões (mínimas):
#   - dataset gold: READER (só leitura, só esse dataset)
#   - projeto: bigquery.jobUser (rodar consultas) + bigquery.readSessionUser (download rápido via Storage API)
#
# Gera data/secrets/streamlit_secrets.toml (fora do Git) para colar em
# share.streamlit.io -> app -> Settings -> Secrets.
#
# Uso: bash scripts/setup_streamlit_sa.sh [projeto] [dataset]
set -euo pipefail

PROJECT="${1:-echo-lead}"
DATASET="${2:-gold}"
NAME="streamlit-dashboard"
SA="${NAME}@${PROJECT}.iam.gserviceaccount.com"
OUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/data/secrets"
KEY="${OUT_DIR}/${NAME}.json"
SECRETS="${OUT_DIR}/streamlit_secrets.toml"

echo "Projeto: ${PROJECT} | dataset: ${DATASET} | conta: ${SA}"
gcloud services enable iam.googleapis.com bigquerystorage.googleapis.com --project "$PROJECT"

if ! gcloud iam service-accounts describe "$SA" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$NAME" --project "$PROJECT" \
    --display-name "Painel Streamlit (leitura gold)"
fi

for ROLE in roles/bigquery.jobUser roles/bigquery.readSessionUser; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${SA}" \
    --role "$ROLE" --condition=None --format=none
done

# Leitura só no dataset gold (ACL do dataset, não do projeto inteiro)
TMP="$(mktemp)"
bq show --format=prettyjson "${PROJECT}:${DATASET}" > "$TMP"
python3 - "$TMP" "$SA" <<'EOF'
import json, sys
path, sa = sys.argv[1], sys.argv[2]
ds = json.load(open(path))
entry = {"role": "READER", "userByEmail": sa}
if entry not in ds.setdefault("access", []):
    ds["access"].append(entry)
json.dump(ds, open(path, "w"))
EOF
bq update --source "$TMP" "${PROJECT}:${DATASET}" >/dev/null
rm -f "$TMP"

mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"
if [[ ! -f "$KEY" ]]; then
  gcloud iam service-accounts keys create "$KEY" --iam-account "$SA" --project "$PROJECT"
  chmod 600 "$KEY"
fi

python3 - "$KEY" "$SECRETS" "${PROJECT}.${DATASET}" <<'EOF'
import json, sys
key, out, dataset = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
lines = [f'bq_dataset = "{dataset}"', "", "[gcp_service_account]"]
for k, v in key.items():
    lines.append(f"{k} = {json.dumps(v)}")
open(out, "w").write("\n".join(lines) + "\n")
EOF
chmod 600 "$SECRETS"

echo
echo "Pronto. Cole o conteúdo de ${SECRETS} em share.streamlit.io -> Settings -> Secrets."
echo "Não commite esse arquivo nem a chave (${KEY})."
