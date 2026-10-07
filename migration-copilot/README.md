# AI Migration Copilot: beginner's runbook

The Migration Copilot is an AI assistant that helps move virtual machines (VMs) from
**VMware** to **Red Hat OpenShift Virtualization**. You chat with it in plain English, and it:

1. **Discovers** the VMs in VMware vCenter (read-only)
2. **Assesses** each VM: is it ready to move, does it need prep work, or is it blocked?
3. **Plans waves**: groups the safest VMs into a first migration batch
4. **Runs** the migration, but only after a named person approves it
5. **Reports** progress

You can use one of two AI "brains":

| Provider | Model family | You need |
| --- | --- | --- |
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
- [Path C: Connect a real lab](#path-c-connect-a-real-lab)
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
├── requirements.txt          ← Python libraries to install
├── demo_local.py             ← quick demo with no AI
├── chat_local.py             ← chat with the Copilot using Claude or GPT on your laptop
├── agents/
│   └── migration_copilot.yaml ← the agent's "personality": rules and tool list
├── tools/
│   ├── vcenter_tools.py      ← reads VMware and scores readiness
│   ├── openshift_tools.py    ← creates and runs MTV plans, checks progress
│   └── tool_spec.py          ← turns each tool function into a spec the AI can call
├── openshift/
│   └── rbac.yaml             ← locked-down OpenShift account for the Copilot
└── docs/
    └── architecture.svg      ← diagram of how the pieces connect
```

### `.env.example`
**What it is:** A template listing every setting the project uses: vCenter address, OpenShift
address, MTV names, and your AI provider and API key.
**How to use it:** Copy it to `.env` (`cp .env.example .env`) and fill in the values you need.
For Paths A and B you only need the AI lines. **Never commit `.env` to git.** It holds secrets.

### `requirements.txt`
**What it is:** The Python libraries to install: `anthropic` and `openai` for the AI,
`pyvmomi` for VMware, `kubernetes` for OpenShift, and `PyYAML`.

**How to use it:** `pip install -r requirements.txt`

### `demo_local.py`
**What it does:** Prints a readiness table for the sample "finance" VMs and the draft MTV
plan the Copilot would create. It doesn't use AI or need a network connection.
**When to use it:** To check your setup works, or to show the logic without any AI.
**How:** `python demo_local.py`

### `chat_local.py`
**What it does:** Starts a chat in your terminal with the Copilot, using **Claude (Anthropic)**
or **GPT (OpenAI)**. It loads the tools from `tools/` and the instructions from
`agents/migration_copilot.yaml`. When the AI calls a tool, you see a `[tool]` line.
**When to use it:** To rehearse the full conversation, or to compare Claude and GPT answers.
**How:**
```bash
python chat_local.py --llm anthropic                  # uses ANTHROPIC_API_KEY
python chat_local.py --llm openai                     # uses OPENAI_API_KEY
python chat_local.py --llm openai --model gpt-4o      # pick a specific model
```
It reads keys and lab settings from `.env` automatically. Type `exit` to quit.

### `agents/migration_copilot.yaml`
**What it is:** The agent definition that `chat_local.py` reads. The model is chosen with
`--llm` and `--model` when you start the chat.
- `instructions:` sets the rules the AI must follow, such as "assess before planning",
  "dry run first" and "only Emmanuel Naweji can approve a migration".
- `tools:` lists which tools the agent may call. Each must be a function in `tools/`.

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
**How to use it:** `oc apply -f openshift/rbac.yaml` (Path C).

### `docs/architecture.svg`
A diagram of how the chat, agent, tools, vCenter and OpenShift fit together, and where each
AI model runs. Anthropic and OpenAI are called directly with your API key and run outside
your agency boundary. Open it in a browser.

---

## Step 0: Install the basics

You need **Python 3.11 or newer** (check with `python3 --version`).

```bash
cd migration-copilot
python3 -m venv venv                 # create an isolated Python environment
source venv/bin/activate             # turn it on (Windows: venv\Scripts\activate)
pip install -r requirements.txt
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
fin-db-01     Blocked              35  Uses a raw device mapping (RDM) disk; ...
```

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

## Path C: Connect a real lab

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
   Optional: `VCENTER_CA_CERT` and `OCP_CA_CERT` take paths to CA certificate files.
5. **Start the chat**
   ```bash
   python chat_local.py --llm anthropic     # or --llm openai
   ```
   Tool replies now say `"mode": "live"` instead of `"demo"`. Leave `VCENTER_URL` and
   `OCP_API_URL` empty to go back to demo mode.

---

## Guardrails

- Discovery is **read-only**. Plans are **dry runs** until you say otherwise.
- **Only Emmanuel Naweji can approve a migration.** `start_migration` refuses to run without
  `approval_confirmed=true` and an approver on the authorized list. To change the list, set
  `MIGRATION_APPROVERS` in `.env` (comma-separated full names) and restart the chat, or edit
  `AUTHORIZED_APPROVERS` in `tools/openshift_tools.py`. Refused attempts are logged as
  `AUDIT migration_rejected`. The approver, time and change ticket are written onto the MTV Migration object and logged
  as an `AUDIT` line. Send tool logs to your SIEM.
- Credentials (vCenter, OpenShift, Anthropic, OpenAI) live in your local `.env`, **never in code**.
- The OpenShift service account can only create MTV plans and migrations and read VMs.
- **Choosing Anthropic or OpenAI sends data outside your boundary.** Prompts and tool results
  (VM names, sizes, OS, plan details) go to that provider. Check your agency's data policy
  first.
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
| `ModuleNotFoundError` (for example `anthropic` or `openai`) | `pip install -r requirements.txt` with the venv on |
| `ANTHROPIC_API_KEY is not set` | Add it to `.env`, or `export ANTHROPIC_API_KEY=...` |
| `401` / `authentication_error` | The API key is wrong or revoked. Create a new one |
| `model not found` | Change `ANTHROPIC_MODEL` / `OPENAI_MODEL` to a model your account can use |
| Live mode when you wanted demo mode | Empty `VCENTER_URL` and `OCP_API_URL` in `.env` |
| Agent won't start a migration | Working as designed. Emmanuel Naweji (or someone in `MIGRATION_APPROVERS`) must approve by name |

---

## Next steps

- Add an inventory/CMDB tool (owner, app, environment) to group waves by application.
- Add a report tool that writes a daily wave summary for leadership.
- Host the Copilot behind a web chat page so people don't need a terminal.
