#!/usr/bin/env bash
# Provision the Azure resources Athenaeum needs, billed to the Azure sponsorship credit:
#   1. Register the Microsoft.Search resource provider
#   2. Create a dedicated resource group (easy teardown)
#   3. Create an Azure AI Search service (Basic) — hosts the Foundry IQ knowledge base
#   4. Deploy text-embedding-3-large on the existing AIServices account (index vectorizer)
#   5. Write SEARCH_ENDPOINT + SEARCH_ADMIN_KEY back into .env
#
# Idempotent: re-running skips resources that already exist. First-party Microsoft.Search is
# covered by the sponsorship credit and is NOT blocked by the deny-real-money policy (which
# only blocks marketplace/SaaS/reservation purchases).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE not found (copy .env.example)."; exit 1; }
set -a; # shellcheck disable=SC1090
source "$ENV_FILE"; set +a

: "${AZURE_LOCATION:?}"; : "${SEARCH_RESOURCE_GROUP:?}"; : "${SEARCH_SERVICE_NAME:?}"
: "${SEARCH_SKU:?}"; : "${AOAI_ACCOUNT_NAME:?}"; : "${AOAI_RESOURCE_GROUP:?}"
: "${EMBED_DEPLOYMENT:?}"; : "${EMBED_MODEL:?}"

echo "==> 1/5 Registering Microsoft.Search provider"
az provider register --namespace Microsoft.Search --wait

echo "==> 2/5 Resource group $SEARCH_RESOURCE_GROUP"
# RG location is independent of the resources inside it; only create if absent.
if az group show --name "$SEARCH_RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "    already exists ($(az group show --name "$SEARCH_RESOURCE_GROUP" --query location -o tsv)) — skipping"
else
  az group create --name "$SEARCH_RESOURCE_GROUP" --location "$AZURE_LOCATION" --output none
fi

echo "==> 3/5 Azure AI Search service $SEARCH_SERVICE_NAME (sku=$SEARCH_SKU)"
if az search service show --name "$SEARCH_SERVICE_NAME" --resource-group "$SEARCH_RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "    already exists — skipping"
else
  az search service create \
    --name "$SEARCH_SERVICE_NAME" \
    --resource-group "$SEARCH_RESOURCE_GROUP" \
    --location "$AZURE_LOCATION" \
    --sku "$SEARCH_SKU" \
    --output none
fi

echo "==> 4/5 Embedding deployment $EMBED_DEPLOYMENT on $AOAI_ACCOUNT_NAME"
if az cognitiveservices account deployment show \
     --name "$AOAI_ACCOUNT_NAME" --resource-group "$AOAI_RESOURCE_GROUP" \
     --deployment-name "$EMBED_DEPLOYMENT" >/dev/null 2>&1; then
  echo "    already exists — skipping"
else
  az cognitiveservices account deployment create \
    --name "$AOAI_ACCOUNT_NAME" \
    --resource-group "$AOAI_RESOURCE_GROUP" \
    --deployment-name "$EMBED_DEPLOYMENT" \
    --model-name "$EMBED_MODEL" \
    --model-version "1" \
    --model-format OpenAI \
    --sku-name "Standard" \
    --sku-capacity 50 \
    --output none
fi

echo "==> 5/5 Resolving Search endpoint + admin key, writing to .env"
SEARCH_HOST="https://${SEARCH_SERVICE_NAME}.search.windows.net"
ADMIN_KEY="$(az search admin-key show \
  --service-name "$SEARCH_SERVICE_NAME" \
  --resource-group "$SEARCH_RESOURCE_GROUP" \
  --query primaryKey -o tsv)"

# Update .env in place (portable across macOS/Linux sed by rewriting the lines).
python3 - "$ENV_FILE" "$SEARCH_HOST" "$ADMIN_KEY" <<'PY'
import sys, re, pathlib
path, host, key = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(path); lines = p.read_text().splitlines()
def setk(lines, k, v):
    out, seen = [], False
    for ln in lines:
        if re.match(rf"^{re.escape(k)}=", ln):
            out.append(f"{k}={v}"); seen = True
        else:
            out.append(ln)
    if not seen: out.append(f"{k}={v}")
    return out
lines = setk(lines, "SEARCH_ENDPOINT", host)
lines = setk(lines, "SEARCH_ADMIN_KEY", key)
p.write_text("\n".join(lines) + "\n")
print(f"    SEARCH_ENDPOINT={host}")
print("    SEARCH_ADMIN_KEY=<written, hidden>")
PY

echo "Done. Next: 'athenaeum ingest'."
