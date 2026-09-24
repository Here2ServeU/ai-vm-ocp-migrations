# AI Migration Copilot: beginner's runbook

The Migration Copilot is an AI assistant that helps move virtual machines (VMs) from
**VMware** to **Red Hat OpenShift Virtualization**. You chat with it in plain English, and it:

1. **Discovers** the VMs in VMware vCenter (read-only)
2. **Assesses** each VM: is it ready to move, does it need prep work, or is it blocked?
3. **Plans waves**: groups the safest VMs into a first migration batch
4. **Runs** the migration, but only after a named person approves it
5. **Reports** progress

You can use one of three AI "brains":

| Provider | Model family | You need |
| --- | --- | --- |
| **IBM watsonx** | Granite, Llama and others | A watsonx / Orchestrate entitlement |
| **Anthropic** | Claude | An API key from <https://console.anthropic.com> |
| **OpenAI** | GPT | An API key from <https://platform.openai.com> |

> **Safe by default.** Until you connect real systems, everything runs in **demo mode**.
> It uses made-up sample VMs and changes nothing, so it's safe to try and to present.

---

## Contents

- [Words you'll see](#words-youll-see)
- [What each file is](#what-each-file-is)
- [Step 0: Install the basics](#step-0-install-the-basics)
- [Path A: See the output with no AI (2 minutes)](#path-a-see-the-output-with-no-ai-2-minutes)
- [Path B: Chat with Claude or GPT on your laptop (5 minutes)](#path-b-chat-with-claude-or-gpt-on-your-laptop-5-minutes)
- [Path C: Run it in watsonx Orchestrate](#path-c-run-it-in-watsonx-orchestrate)
- [Path D: Connect a real lab](#path-d-connect-a-real-lab)
- [Guardrails](#guardrails)
- [Readiness rules](#readiness-rules)
- [Troubleshooting](#troubleshooting)
- [Next steps](#next-steps)

---

## Words you'll see

| Term | Plain meaning |
| --- | --- |
| **VM** | A virtual machine, a computer that runs as software on a server |
| **vCenter** | VMware's management console. It knows about every VM |
| **OpenShift Virtualization** | Red Hat's platform for running VMs on OpenShift (Kubernetes) |
| **MTV** | *Migration Toolkit for Virtualization*, the Red Hat add-on that copies VMs from VMware to OpenShift |
| **Plan / Migration** | In MTV, a **Plan** lists which VMs to move and where. A **Migration** is one run of that plan |
| **Wave** | A batch of VMs migrated together |
| **Warm migration** | Copies data while the VM keeps running, so downtime is shorter |
| **watsonx Orchestrate** | IBM's platform for hosting AI agents. It's the "production" home for this Copilot |
| **Agent** | The AI assistant: a model, instructions and a set of tools it can call |
| **Tool** | A Python function the agent can call, such as "list VMs" |
| **LLM / model** | The AI that reads your question and decides which tools to call |
| **API key** | A secret password that lets a program use Anthropic's or OpenAI's AI service |
| **Demo mode** | No real connections are set up, so the tools return sample data and change nothing |

---

## What each file is

```
migration-copilot/
├── README.md                 ← this runbook
├── .env.example              ← template for your settings and secrets
├── requirements.txt          ← Python libraries the tools need (uploaded to Orchestrate)
├── requirements-local.txt    ← extra libraries for running on your laptop
├── demo_local.py             ← quick demo with no AI
├── chat_local.py             ← chat with the Copilot using Claude or GPT on your laptop
├── agents/
│   └── migration_copilot.yaml ← the agent's "personality": model, rules, tool list
├── tools/
│   ├── vcenter_tools.py      ← reads VMware and scores readiness
│   └── openshift_tools.py    ← creates and runs MTV plans, checks progress
├── openshift/
│   └── rbac.yaml             ← locked-down OpenShift account for the Copilot
├── scripts/
│   └── setup.sh              ← one command to load everything into Orchestrate
└── docs/
    └── architecture.svg      ← diagram of how the pieces connect
```

### `.env.example`
**What it is:** A template listing every setting the project uses: vCenter address, OpenShift
address, MTV names, and your AI provider and API key.
**How to use it:** Copy it to `.env` (`cp .env.example .env`) and fill in the values you need.
For Paths A and B you only need the AI lines. **Never commit `.env` to git.** It holds secrets.

### `requirements.txt` and `requirements-local.txt`
**What they are:** Lists of Python libraries to install.
- `requirements.txt` is what the tools need to run (`pyvmomi` for VMware, `kubernetes` for
  OpenShift, `PyYAML`). Orchestrate installs these when you upload the tools.
- `requirements-local.txt` adds what your laptop needs: the Orchestrate SDK, plus the
  `anthropic` and `openai` libraries.

**How to use them:** `pip install -r requirements-local.txt`

### `demo_local.py`
**What it does:** Prints a readiness table for the sample "finance" VMs and the draft MTV
plan the Copilot would create. It doesn't use AI or need a network connection.
**When to use it:** To check your setup works, or to show the logic without any AI.
**How:** `python demo_local.py`

### `chat_local.py`
**What it does:** Starts a chat in your terminal with the Copilot, using **Claude (Anthropic)**
or **GPT (OpenAI)**. It uses the same tools and the same instructions as the real agent,
without an Orchestrate server. When the AI calls a tool, you see a `[tool]` line.
**When to use it:** To rehearse the full conversation, or to compare Claude and GPT answers.
**How:**
```bash
python chat_local.py --llm anthropic                  # uses ANTHROPIC_API_KEY
python chat_local.py --llm openai                     # uses OPENAI_API_KEY
python chat_local.py --llm openai --model gpt-4o      # pick a specific model
```
It reads keys from `.env` automatically. Type `exit` to quit.

### `agents/migration_copilot.yaml`
**What it is:** The agent definition used by Orchestrate (and by `chat_local.py` for its instructions).
- `llm:` sets which model to use. `setup.sh --llm` swaps this for you, so you don't edit it by hand.
- `instructions:` sets the rules the AI must follow, such as "assess before planning",
  "dry run first" and "only Emmanuel Naweji can approve a migration".
- `tools:` lists which tools the agent may call.

**How to use it:** Edit `instructions:` to change the Copilot's behavior or tone.

### `tools/vcenter_tools.py` (read-only)
**What it does:** Talks to VMware vCenter. It never changes anything there.
- `discover_vms` lists VMs with CPU, memory, disk, OS, readiness and risk score.
- `readiness_summary` gives counts per readiness group and the top blockers, which is useful for leadership questions.
- `assess()` holds the readiness rules. Edit it to change what counts as "Blocked".
- `SAMPLE_VMS` holds the fake VMs used in demo mode. Edit freely.

### `tools/openshift_tools.py`
**What it does:** Talks to OpenShift and MTV.
- `create_migration_plan` drafts an MTV plan. It's a **dry run by default**, so nothing is saved.
- `start_migration` starts a plan. It **refuses** unless `approval_confirmed=true` and the approver is on the authorized list (`AUTHORIZED_APPROVERS`, default **Emmanuel Naweji**). It writes an audit record, including refused attempts.
- `migration_status` shows per-VM progress.
- `list_openshift_vms` lists VMs already running on OpenShift.

### `openshift/rbac.yaml`
**What it is:** OpenShift permissions for a service account called `migration-copilot`.
It can only read and create MTV plans and migrations and read VMs. It can't delete anything.
**How to use it:** `oc apply -f openshift/rbac.yaml` (Path D).

### `scripts/setup.sh`
**What it does:** Loads everything into your active watsonx Orchestrate environment:
connections (credentials), your chosen AI model, both tool files and the agent.
**How to use it:**
```bash
./scripts/setup.sh --demo                     # sample data, watsonx model
./scripts/setup.sh --demo --llm anthropic     # sample data, Claude
./scripts/setup.sh --demo --llm openai        # sample data, GPT
./scripts/setup.sh --llm anthropic            # real vCenter/OpenShift, Claude
```
Leave out `--demo` only when you've filled in the vCenter and OpenShift values (Path D).

### `docs/architecture.svg`
A diagram of how the chat, agent, tools, vCenter and OpenShift fit together. Open it in a browser.

---

## Step 0: Install the basics

You need **Python 3.11 or newer** (check with `python3 --version`).

```bash
cd migration-copilot
python3 -m venv venv                 # create an isolated Python environment
source venv/bin/activate             # turn it on (Windows: venv\Scripts\activate)
pip install -r requirements-local.txt
cp .env.example .env                 # your personal settings file
```

You'll see `(venv)` at the start of your prompt while the environment is on. Run
`source venv/bin/activate` again whenever you open a new terminal.

---

## Path A: See the output with no AI (2 minutes)

```bash
python demo_local.py
```

You should see a table like this, followed by a draft plan:

```
[demo mode] finance cluster

VM            Readiness          Risk  Notes
fin-web-01    Ready                 0  -
fin-app-01    Ready                 0  -
fin-web-02    Ready with prep      10  Remove or consolidate snapshots before migrating
fin-db-01     Blocked              45  Uses a raw device mapping (RDM) disk; ...
```

A `No credentials found for connections 'vcenter'` line is normal. It means you're in demo mode.

---

## Path B: Chat with Claude or GPT on your laptop (5 minutes)

1. **Get an API key**
   - Anthropic: <https://console.anthropic.com> → *API Keys* → *Create key*
   - OpenAI: <https://platform.openai.com/api-keys> → *Create new secret key*
2. **Put it in `.env`**. Open `.env` and fill in one of these:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   OPENAI_API_KEY=sk-...
   ```
   To change the model, edit `ANTHROPIC_MODEL` or `OPENAI_MODEL`.
3. **Start chatting**
   ```bash
   python chat_local.py --llm anthropic     # or --llm openai
   ```
4. **Try this conversation**
   ```
   you> How ready is the finance cluster to move?
   you> Draft wave 1 with the lowest-risk VMs into the finance-prod project.
   you> Start it.                              ← it should ask who approves and for a ticket
   you> Approved by Jane Smith, ticket CHG-1234.     ← refused: Jane isn't an authorized approver
   you> Approved by Emmanuel Naweji, ticket CHG-1234.
   you> What's the status?                     ← ask a few times to watch progress
   ```

Each question costs a small amount on your Anthropic or OpenAI account.

---

## Path C: Run it in watsonx Orchestrate

This is the "real" home for the agent, with a web chat UI and credentials stored safely.

**You need:** Docker (via Rancher Desktop or Colima), about **16 GB RAM and 8 CPU cores** free,
and your watsonx Orchestrate entitlement settings in `.env`. See IBM's ADK docs for those values.

```bash
set -a; source .env; set +a              # load your settings into this terminal
orchestrate server start -e .env         # start Orchestrate Developer Edition (first run takes a while)
orchestrate env activate local

# Pick ONE:
./scripts/setup.sh --demo                     # IBM watsonx model (from agents/migration_copilot.yaml)
./scripts/setup.sh --demo --llm anthropic     # Claude, uses ANTHROPIC_API_KEY
./scripts/setup.sh --demo --llm openai        # GPT,    uses OPENAI_API_KEY

orchestrate chat start                   # opens the chat UI in your browser
```

**How the model choice works:**
- `watsonx` uses the `llm:` line in `agents/migration_copilot.yaml`. Run
  `orchestrate models list` to see which models your environment has, then edit that line.
- `anthropic` / `openai`: the script saves your API key in an Orchestrate connection
  (`anthropic_creds` or `openai_creds`), registers the model with `orchestrate models add`,
  and imports the agent with `llm: virtual-model/<provider>/<model>`. Your checked-in YAML file
  isn't changed.

To switch providers later, run `setup.sh` again with a different `--llm`.

---

## Path D: Connect a real lab

Only do this in a **test lab** first. Start with 5–10 throwaway VMs.

1. **Install MTV** on OpenShift (OperatorHub → *Migration Toolkit for Virtualization*).
   In the MTV console, create a **vSphere provider**, a **NetworkMap** and a **StorageMap**.
   Write down their names.
2. **Create the Copilot's OpenShift account**
   ```bash
   oc apply -f openshift/rbac.yaml
   oc create token migration-copilot -n openshift-mtv --duration=8h   # copy the output
   # Let it read VMs in each target project:
   oc create rolebinding migration-copilot-view -n <project> \
     --clusterrole=migration-copilot-vm-viewer --serviceaccount=openshift-mtv:migration-copilot
   ```
3. **Create a read-only vCenter user** for discovery (ask your VMware admin).
4. **Fill in `.env`**: `VCENTER_URL`, `VCENTER_USER`, `VCENTER_PASSWORD`, `OCP_API_URL`,
   `OCP_TOKEN` (from step 2), `MTV_SOURCE_PROVIDER`, `MTV_NETWORK_MAP`, `MTV_STORAGE_MAP`.
5. **Load and run**
   ```bash
   set -a; source .env; set +a
   ./scripts/setup.sh --llm anthropic      # or openai / watsonx
   orchestrate chat start
   ```
   Tool replies now say `"mode": "live"` instead of `"demo"`.

> `chat_local.py` always runs in demo mode, because real credentials come from Orchestrate
> connections. Use Orchestrate (Path C/D) for live systems.

---

## Guardrails

- Discovery is **read-only**. Plans are **dry runs** until you say otherwise.
- **Only Emmanuel Naweji can approve a migration.** `start_migration` refuses to run without
  `approval_confirmed=true` and an approver on the authorized list. To change the list, set
  `MIGRATION_APPROVERS` in `.env` (comma-separated full names) and rerun `setup.sh`, or edit
  `AUTHORIZED_APPROVERS` in `tools/openshift_tools.py`. Refused attempts are logged as
  `AUDIT migration_rejected`. The approver, time and change ticket are written onto the MTV Migration object and logged
  as an `AUDIT` line. Send tool logs to your SIEM.
- Credentials (vCenter, OpenShift, Anthropic, OpenAI) live in Orchestrate connections or
  your local `.env`, **never in code**.
- The OpenShift service account can only create MTV plans and migrations and read VMs.
- These rules are enforced in code, not only in the AI's instructions, so they hold whichever model you choose.

---

## Readiness rules

Edit these in `assess()` in `tools/vcenter_tools.py`.

| Result | Meaning |
| --- | --- |
| Ready | No issues found |
| Ready with prep | Snapshots, very large disks or very large VM |
| Blocked | RDM disk, shared multi-writer disk, PCI passthrough, or guest OS to review |
| Retire candidate | Powered off. Confirm with the owner before moving it |

Always confirm guest OS support against Red Hat's current OpenShift Virtualization
documentation. These rules are a starting point, not a certification.

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `command not found: python` | Use `python3`, or turn on the venv: `source venv/bin/activate` |
| `ModuleNotFoundError: ibm_watsonx_orchestrate` (or `anthropic` / `openai`) | `pip install -r requirements-local.txt` with the venv on |
| `ANTHROPIC_API_KEY is not set` | Add it to `.env`, or `export ANTHROPIC_API_KEY=...` |
| `401` / `authentication_error` | The API key is wrong or revoked. Create a new one |
| `model not found` | Change `ANTHROPIC_MODEL` / `OPENAI_MODEL` to a model your account can use |
| `No credentials found for connections 'vcenter'` | Normal in demo mode |
| `setup.sh: set VCENTER_URL` | You left out `--demo` but didn't fill in lab settings. Add `--demo`, or run `set -a; source .env; set +a` |
| `Permission denied: ./scripts/setup.sh` | `chmod +x scripts/setup.sh` |
| Orchestrate server won't start | Check Docker is running and has at least 16 GB RAM |
| Agent won't start a migration | Working as designed. Emmanuel Naweji (or someone in `MIGRATION_APPROVERS`) must approve by name |

---

## Next steps

- Add an inventory/CMDB tool (owner, app, environment) to group waves by application.
- Add a report tool that writes a daily wave summary for leadership.
- Add watsonx.governance to track the model's decisions.
