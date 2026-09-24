#!/usr/bin/env bash
# Import the Migration Copilot into your ACTIVE watsonx Orchestrate environment.
# Local first:  orchestrate server start -e .env   then   orchestrate env activate local
#
# Options:
#   --demo                     skip vCenter/OpenShift connections; tools use sample data
#   --llm watsonx|anthropic|openai
#                              which AI model provider the agent uses (default: $LLM_PROVIDER or watsonx)
#
# anthropic needs ANTHROPIC_API_KEY (model: $ANTHROPIC_MODEL, default claude-sonnet-5)
# openai    needs OPENAI_API_KEY    (model: $OPENAI_MODEL,    default gpt-4.1)
set -euo pipefail
cd "$(dirname "$0")/.."

DEMO=false
LLM="${LLM_PROVIDER:-watsonx}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo) DEMO=true ;;
    --llm)  LLM="${2:?--llm needs watsonx, anthropic or openai}"; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

if [[ "$DEMO" == false ]]; then
  orchestrate connections add -a vcenter || true
  orchestrate connections configure -a vcenter --env draft --type team --kind basic \
    --url "${VCENTER_URL:?set VCENTER_URL}"
  orchestrate connections set-credentials -a vcenter --env draft \
    -u "${VCENTER_USER:?}" -p "${VCENTER_PASSWORD:?}"

  orchestrate connections add -a openshift || true
  orchestrate connections configure -a openshift --env draft --type team --kind key_value
  orchestrate connections set-credentials -a openshift --env draft \
    -e "api_url=${OCP_API_URL:?}" -e "token=${OCP_TOKEN:?}" \
    -e "mtv_namespace=${MTV_NAMESPACE:-openshift-mtv}" \
    -e "source_provider=${MTV_SOURCE_PROVIDER:-vsphere}" \
    -e "destination_provider=host" \
    -e "network_map=${MTV_NETWORK_MAP:?}" -e "storage_map=${MTV_STORAGE_MAP:?}"
  APP_V="-a vcenter"; APP_O="-a openshift"
else
  APP_V=""; APP_O=""
fi

# Register an external model (Anthropic or OpenAI) with Orchestrate's AI gateway.
# The API key is stored in an Orchestrate connection, never in the agent file.
add_model() {  # $1 = provider, $2 = model, $3 = API key
  orchestrate connections add -a "$1_creds" || true
  orchestrate connections configure -a "$1_creds" --env draft --type team --kind key_value
  orchestrate connections set-credentials -a "$1_creds" --env draft -e "api_key=$3"
  orchestrate models add --name "$1/$2" --app-id "$1_creds" || true  # ok if already added
  AGENT_LLM="virtual-model/$1/$2"
}

AGENT_LLM=""
case "$LLM" in
  watsonx)   ;;  # keep the llm: line in agents/migration_copilot.yaml
  anthropic) add_model anthropic "${ANTHROPIC_MODEL:-claude-sonnet-5}" "${ANTHROPIC_API_KEY:?set ANTHROPIC_API_KEY}" ;;
  openai)    add_model openai "${OPENAI_MODEL:-gpt-4.1}" "${OPENAI_API_KEY:?set OPENAI_API_KEY}" ;;
  *) echo "--llm must be watsonx, anthropic or openai (got: $LLM)" >&2; exit 1 ;;
esac

orchestrate tools import -k python -f tools/vcenter_tools.py   -r requirements.txt $APP_V
orchestrate tools import -k python -f tools/openshift_tools.py -r requirements.txt $APP_O

AGENT_FILE=agents/migration_copilot.yaml
if [[ -n "$AGENT_LLM" ]]; then
  # Import a copy with the llm: line swapped, so the checked-in file stays unchanged.
  TMP_AGENT="$(mktemp -t migration_copilot).yaml"
  sed "s|^llm:.*|llm: $AGENT_LLM|" "$AGENT_FILE" > "$TMP_AGENT"
  AGENT_FILE="$TMP_AGENT"
fi
orchestrate agents import -f "$AGENT_FILE"
echo "Done (model provider: $LLM${AGENT_LLM:+, $AGENT_LLM}). Try: orchestrate chat start"
