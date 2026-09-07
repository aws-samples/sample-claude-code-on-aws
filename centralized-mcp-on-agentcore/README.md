# Build a centralized MCP server gateway with Amazon Bedrock AgentCore

When working with multiple Model Context Protocol (MCP) servers, managing authentication and authorization for each backend can become complex. As the number of tools grows, development teams often find themselves embedding access control logic into individual backends, duplicating OAuth token validation across services, and struggling to maintain consistent security policies — whether building a proof-of-concept or an enterprise solution.

[Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) provides a centralized gateway that simplifies this challenge by unifying authentication and authorization across multiple tool backends in a single managed endpoint.

With AgentCore Gateway, you can connect [AWS Lambda](https://aws.amazon.com/lambda/) functions as tool backends behind one managed MCP proxy that enforces [Cedar](https://www.cedarpolicy.com/) policies for fine-grained access control — centralizing authentication, authorization, and tool routing in one place.

In this post, we walk through four Jupyter notebooks that progressively build a complete, working demo:

1. **`00_okta_setup.ipynb`** — Configure an external identity provider (Okta) for OAuth authentication
2. **`01_agentcore_setup.ipynb`** — Deploy Lambda tool backends, create the AgentCore Gateway, and define Cedar access policies
3. **`02_claude_code_setup.ipynb`** — Connect [Claude Code](https://docs.anthropic.com/en/docs/claude-code) to the gateway using native MCP OAuth support
4. **`03_registry_demo.ipynb`** — Publish tools to the AgentCore Registry for centralized discovery and governance

## Prerequisites

Before you begin, you need the following:

- An AWS account with permissions to create Lambda functions, IAM roles, and AgentCore resources
- [Terraform](https://www.terraform.io/) (infrastructure-as-code tool) v1.5 or later installed
- An [Okta](https://www.okta.com/) developer account (free identity provider for OAuth authentication) or compatible OIDC provider, with an authorization server configured
- Python 3.12 or later with [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) (the AWS SDK for Python) and the [AgentCore SDK](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html) installed
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (Anthropic's AI coding assistant CLI) installed on your local machine

### Getting started resources

If you're new to any of the prerequisites, the following resources can help:

- **New to AWS?** Start with the [AWS Getting Started Guide](https://aws.amazon.com/getting-started/)
- **Need to learn Terraform?** See [Terraform tutorials](https://developer.hashicorp.com/terraform/tutorials)
- **New to Okta or OIDC?** See [Okta Developer Getting Started](https://developer.okta.com/docs/guides/)
- **Setting up Python?** See [Python installation guide](https://www.python.org/about/gettingstarted/)
- **Installing Claude Code?** See [Claude Code quickstart](https://docs.anthropic.com/en/docs/claude-code/overview)

## Solution overview

The solution consists of three layers: tool backends, a managed gateway, and AI agent clients.

The following diagram illustrates the architecture:

```
┌──────────────────────────────┐
│     AI Agent Clients         │
│  (Claude Code, custom apps)  │
│  OAuth token in each request │
└─────────────┬────────────────┘
              │ MCP Streamable HTTP + JWT
              ▼
┌──────────────────────────────┐
│  AgentCore Gateway           │
│  ┌────────────────────────┐  │
│  │ JWT Validation (Okta)  │  │
│  │ Cedar Policy Engine    │  │
│  │ Tool Discovery Filter  │  │
│  │ Request Routing        │  │
│  └────────────────────────┘  │
└──┬──────────────────────┬────┘
   ▼                      ▼
┌────────────────┐ ┌────────────────┐
│ Lambda         │ │ Lambda         │
│ PolicyLookup   │ │ ClaimsData     │
└────────────────┘ └────────────────┘
```

The preceding figure illustrates the following workflow:

1. An AI agent client sends an MCP request to the AgentCore Gateway with a JWT bearer token
2. The gateway validates the JWT signature against the identity provider's JWKS endpoint
3. The Cedar policy engine evaluates whether the authenticated user is permitted to discover or invoke the requested tool
4. If permitted, the gateway routes the request to the appropriate Lambda function target
5. The Lambda function processes the request and returns results through the gateway to the client

The key benefit of this architecture is that individual backends contain zero access control logic. This means each backend service focuses solely on its business logic, while the gateway handles all authentication and authorization decisions centrally, reducing code duplication and security complexity.

## Step 1: Configure the identity provider (`00_okta_setup.ipynb`)

The AgentCore Gateway validates JWTs issued by an external identity provider. Before creating any AWS resources, run **`00_okta_setup.ipynb`** to configure your Okta authorization server with the claims and scopes the gateway requires.

This notebook automates the following setup:

- **Custom scopes and claims** — Adds a `groups` scope and a `client_id` claim to the default authorization server. The `client_id` claim is essential because AgentCore Gateway checks the `allowedClients` list against this claim, and Okta uses `cid` by default.
- **SPA application for Claude Code** — Creates a public client (Single Page Application) configured for Authorization Code + PKCE. Claude Code uses this app to authenticate without a client secret. The resulting `OKTA_SPA_CLIENT_ID` is written to `.env` for subsequent notebooks.
- **Demo users and groups** — Creates two users (Alex in the `analysts` group, Jordan in the `finance-admins` group) that map to Cedar policy principals in later steps.

After running this notebook, your `.env` file contains `OKTA_DOMAIN`, `OKTA_SPA_CLIENT_ID`, and demo user credentials — everything needed by the remaining notebooks.

> **Note:** This notebook requires an Okta API token with admin access. For production environments, use scoped OAuth 2.0 service apps instead of API tokens and store secrets in a secrets manager.

## Step 2: Deploy infrastructure and create the gateway (`01_agentcore_setup.ipynb`)

This is the core notebook. **`01_agentcore_setup.ipynb`** deploys all AWS infrastructure and configures the AgentCore Gateway with Cedar policy-based access control. It contains six cells that build up the solution layer by layer.

### Deploy Lambda tool backends (Cells 2–3)

The notebook runs `terraform apply` to deploy two Lambda functions that serve as tool backends for an insurance demo scenario:

- **PolicyLookup** — A read-only policy database that returns insurance policy details by policy number
- **ClaimsData** — A confidential claims service that supports query filtering and user-based restrictions

The PolicyLookup handler is straightforward:

```python
def lambda_handler(event, context):
    policy_number = event.get("policy_number", "")

    policies = {
        "POL-10042": {
            "holder": "Sarah Chen",
            "type": "Homeowners",
            "coverage_limit": 750000,
            "status": "Active"
        },
        # Additional policies defined here
    }

    if policy_number in policies:
        return {"status": "found", "policy": policies[policy_number]}
    return {"status": "not_found", "message": f"No policy found for {policy_number}"}
```

The ClaimsData handler demonstrates how the gateway propagates caller identity to backends. The gateway injects a `requestContext` object into the Lambda event containing the JWT `sub` claim, enabling per-user filtering without any authentication code in the Lambda itself:

```python
def lambda_handler(event, context):
    query = event.get("query", "")
    max_amount = event.get("max_amount", None)

    request_context = event.get("context", {}).get("requestContext", {})
    caller_sub = request_context.get("sub", "")

    contextual_user = os.environ.get("CONTEXTUAL_USER", "")
    if caller_sub == contextual_user and max_amount:
        contextual_limit = int(os.environ.get("CONTEXTUAL_MAX_AMOUNT", "100000"))
        claims = [c for c in claims if c["amount_claimed"] <= contextual_limit]

    return {"status": "success", "claims": matching_claims}
```

After Terraform completes, Cell 3 invokes both Lambda functions directly to verify they are working before wiring them to the gateway.

### Create the gateway with JWT authentication (Cell 4)

Cell 4 creates the AgentCore Gateway with a `CUSTOM_JWT` authorizer that validates tokens against the Okta OIDC discovery endpoint:

```python
agentcore_client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")

response = agentcore_client.create_gateway(
    name="mcp-demo-gateway",
    protocolType="MCP",
    roleArn=GATEWAY_ROLE_ARN,
    authorizerType="CUSTOM_JWT",
    authorizerConfiguration={
        "customJWTAuthorizer": {
            "discoveryUrl": "https://your-domain.okta.com/oauth2/default/.well-known/openid-configuration",
            "allowedAudience": ["api://default"],
            "allowedClients": ["<your-okta-spa-client-id>"]
        }
    }
)
```

The `roleArn` parameter is critical — it assigns an IAM execution role so the gateway can invoke your Lambda functions on your behalf. Without it, the gateway has no AWS identity and cannot reach any backends. Terraform creates this role in Cell 2 with permissions for `lambda:InvokeFunction`.

The notebook then registers each Lambda as a named **target** on the gateway, along with inline tool schemas that define the MCP tool interface:

```python
agentcore_client.create_gateway_target(
    gatewayIdentifier=gateway_id,
    name="PolicyLookup",
    targetConfiguration={
        "mcp": {
            "lambda": {
                "lambdaArn": "<policy-lookup-lambda-arn>",
                "toolSchema": {
                    "inlinePayload": [{
                        "name": "lookup_policy",
                        "description": "Look up insurance policy details by policy number.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "policy_number": {"type": "string", "description": "Policy number (e.g., POL-10042)"}
                            },
                            "required": ["policy_number"]
                        }
                    }]
                }
            }
        }
    }
)
```

When a request arrives, the gateway validates the JWT signature, checks the audience and client ID claims, and maps the `sub` claim to a Cedar principal of type `AgentCore::OAuthUser`.

### Define Cedar policies for access control (Cell 5)

Cell 5 creates a Cedar policy engine and attaches it to the gateway in **ENFORCE** mode, meaning that requests without a matching permit policy are denied. It then defines three authorization patterns that demonstrate the power of Cedar's principal-action-resource model.

**Pattern 1 — Open access for a specific target.** Allow all authenticated users to discover and call the PolicyLookup tool:

```cedar
permit(
    principal is AgentCore::OAuthUser,
    action in [
        AgentCore::Action::"PolicyLookup",
        AgentCore::Action::"PolicyLookup___lookup_policy"
    ],
    resource == AgentCore::Gateway::"<gateway-arn>"
);
```

This policy uses `principal is AgentCore::OAuthUser` (without a specific identifier), which matches any user who holds a valid JWT.

**Pattern 2 — Role-based access for sensitive data.** Restrict the ClaimsData target to a specific user:

```cedar
permit(
    principal == AgentCore::OAuthUser::"jordan@example.com",
    action in [
        AgentCore::Action::"ClaimsData",
        AgentCore::Action::"ClaimsData___query_claims"
    ],
    resource == AgentCore::Gateway::"<gateway-arn>"
);
```

With this policy, only Jordan can see and invoke the ClaimsData tool. Other authenticated users do not see this tool in the tool discovery response — the gateway filters it from the tool list entirely.

**Pattern 3 — Contextual constraints on tool inputs.** Restrict a user's queries to claims below a specific dollar amount:

```cedar
permit(
    principal == AgentCore::OAuthUser::"alex@example.com",
    action == AgentCore::Action::"ClaimsData___query_claims",
    resource == AgentCore::Gateway::"<gateway-arn>"
)
when {
    context.input has "max_amount" &&
    context.input.max_amount <= 100000
};
```

The `when` clause inspects the tool's input parameters at invocation time. If Alex calls `query_claims` with a `max_amount` value exceeding 100,000 or omits the parameter entirely, the gateway denies the request before it reaches the Lambda function. This is the same tool, same gateway — Cedar dynamically controls *what values* you can pass, not just whether you can call the tool.

### Cedar entity model

The following table describes how the gateway maps JWT claims and MCP concepts to Cedar entities:

| Cedar Entity | Maps From | Example |
|---|---|---|
| Principal | JWT `sub` claim | `AgentCore::OAuthUser::"jordan@example.com"` |
| Action (target) | Gateway target name | `AgentCore::Action::"PolicyLookup"` |
| Action (tool) | Target + tool name | `AgentCore::Action::"PolicyLookup___lookup_policy"` |
| Resource | Gateway ARN | `AgentCore::Gateway::"arn:aws:bedrock-agentcore:..."` |
| Context | Tool input parameters | `context.input.max_amount` |

Target-level actions control tool discovery (whether the tool appears in the list). Tool-level actions control invocation (whether the tool can be called with specific inputs).

The notebook finishes by saving all resource identifiers to `gateway_config.json` for the remaining notebooks.

## Step 3: Connect Claude Code to the gateway (`02_claude_code_setup.ipynb`)

With the gateway running and Cedar policies enforced, **`02_claude_code_setup.ipynb`** configures Claude Code to authenticate and connect using its native MCP OAuth support.

### How the OAuth flow works

Claude Code supports MCP OAuth natively, which means it handles the entire Authorization Code + PKCE flow without any custom token management. The key concept is that Claude Code acts as a public client — it uses the SPA application created in `00_okta_setup.ipynb` and authenticates through a browser popup.

The notebook performs three steps:

**1. Update the gateway's `allowedClients` (Cell 2).** The gateway's JWT authorizer maintains a list of client IDs it accepts. Cell 2 adds the SPA client ID so tokens issued during Claude Code's OAuth flow are accepted:

```python
agentcore_client.update_gateway(
    gatewayIdentifier=gateway_id,
    authorizerConfiguration={
        "customJWTAuthorizer": {
            "allowedClients": [existing_client_id, spa_client_id]
        }
    }
)
```

**2. Register the MCP server in Claude Code (Cell 3).** The `claude mcp add-json` command adds the AgentCore Gateway as an MCP server with explicit OAuth configuration:

```bash
claude mcp add-json "agentcore-gateway" '{
  "type": "http",
  "url": "https://<gateway-id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp",
  "oauth": {
    "clientId": "<spa-client-id>",
    "callbackPort": 8400,
    "scope": "openid groups",
    "authorizationUrl": "https://your-domain.okta.com/oauth2/default/v1/authorize",
    "tokenUrl": "https://your-domain.okta.com/oauth2/default/v1/token"
  }
}'
```

The `scope` field requests `openid` (for OIDC) and `groups` (for Cedar identity mapping). The `authorizationUrl` and `tokenUrl` are specified explicitly because Claude Code's MCP OAuth discovery sends a `resource` parameter that Okta doesn't handle without explicit scopes.

**3. Verify the connection.** When Claude Code connects to the gateway, the following flow occurs:

1. Claude Code sends an initial MCP request to the gateway endpoint
2. The gateway returns a `401` response with OAuth discovery metadata
3. Claude Code opens a browser window to the Okta login page
4. After you authenticate, Okta issues an authorization code
5. Claude Code exchanges the code for a JWT using PKCE (no client secret required)
6. The JWT is cached locally in `~/.claude/oauth-tokens/` for subsequent requests
7. Claude Code resends the MCP request with the JWT as a bearer token
8. The gateway validates the token and returns the filtered tool list based on your Cedar policies

### Test different user access levels

After authentication, Claude Code displays only the tools your Cedar policies allow. The following table shows what each demo user sees:

| Login as | Tools visible | ClaimsData access |
|----------|--------------|-------------------|
| **Alex** (analysts group) | `PolicyLookup___lookup_policy` | Blocked — no Cedar permit |
| **Jordan** (finance-admins group) | `PolicyLookup___lookup_policy` + `ClaimsData___query_claims` | Full access |
| **Contextual user** (configured in `.env`) | `PolicyLookup___lookup_policy` + `ClaimsData___query_claims` | Only when `max_amount` is within the Cedar threshold |

You can test the connection by asking Claude Code to look up an insurance policy:

```
> Look up policy POL-10042 for Sarah Chen

Claude Code calls the lookup_policy tool via the AgentCore Gateway
and returns the policy details: Homeowners coverage, $750,000 limit, Active status.
```

To switch users, clear the cached OAuth token and restart Claude Code:

```bash
rm -rf ~/.claude/oauth-tokens/
claude
```

## Step 4: Discover tools through the Registry (`03_registry_demo.ipynb`)

The previous steps demonstrate running tools through the gateway. But in an organization with many teams and tools, how do agents *find* the right tools in the first place? **`03_registry_demo.ipynb`** addresses this with the AgentCore Registry — a managed catalog that lets agents discover approved tools using natural language search.

### Gateway vs. Registry

| Layer | Role | Analogy |
|-------|------|---------|
| **Gateway** | Run tools securely | API gateway / runtime |
| **Registry** | Find the right tool | App store / internal catalog |

The Registry stores tool metadata (names, descriptions, input schemas) — it does not invoke tools. Agents discover tools via the Registry, then invoke them through the Gateway.

### Create the Registry and publish records (Cells 2–3)

The notebook creates a Registry with the same Okta JWT authorizer as the gateway, so agents authenticate once and can both discover and invoke tools:

```python
agentcore_control.create_registry(
    name="open-insurance-registry",
    authorizerType="CUSTOM_JWT",
    authorizerConfiguration={
        "customJWTAuthorizer": {
            "discoveryUrl": "https://your-domain.okta.com/oauth2/default/.well-known/openid-configuration",
            "allowedAudience": ["api://default"],
            "allowedClients": [spa_client_id]
        }
    },
    approvalConfiguration={"autoApproval": False}
)
```

Setting `autoApproval` to `False` enables the governance workflow — records are not searchable until explicitly approved. The notebook then publishes MCP server records for each tool, including the tool schema and installation instructions for Claude Code in the record description.

### Governance workflow (Cell 4)

Records go through a publish-review-approve lifecycle:

```
Developer publishes record → DRAFT
    ↓
Developer submits for review → PENDING_APPROVAL
    ↓
Team lead / curator approves → APPROVED (now searchable)
```

In production, the submit step triggers an EventBridge event that can integrate with ticketing systems or security review workflows. The notebook demonstrates both roles (publisher and curator) to complete the lifecycle.

### Search with JWT authentication (Cell 5)

Cell 5 demonstrates searching the Registry using the same PKCE browser flow that Claude Code uses. After authenticating, the notebook runs semantic searches:

```python
resp = requests.post(
    "https://bedrock-agentcore.<region>.amazonaws.com/registry-records/search",
    headers={"Authorization": f"Bearer {access_token}"},
    json={
        "searchQuery": "insurance policy lookup",
        "registryIds": [registry_arn],
        "maxResults": 10
    }
)
```

The Registry supports natural language queries — searching for "confidential claims adjuster" returns the ClaimsData record even though those exact words may not appear in the tool name.

### Registry-first discovery in Claude Code (Cell 6)

The most powerful pattern in this notebook is the **Registry-first flow**: Claude Code connects only to the Registry at startup, discovers tools through search, then dynamically adds the Gateway connection — all in a single session without restarting.

```
1. Start Claude Code → authenticates to Registry (Okta popup)
2. Ask: "What insurance tools are available?"
   → Registry search returns tools + Gateway install instructions
3. Claude Code reads the install command from the record description
   → Runs: claude mcp add-json agentcore-gateway '...'
4. Run /reload-plugins → connects to Gateway (second Okta popup)
5. Ask: "Look up policy POL-10042"
   → Invokes tool on Gateway with Cedar enforcement
```

This pattern is valuable for regulated industries where least-privilege access matters — users only authenticate to backends they actually need, and each OAuth popup creates an explicit audit trail.

### Publish agent skills (Cells 7–9)

The Registry also supports `AGENT_SKILLS` records — reusable workflows that tell agents *how to reason*, not just *what to call*. The notebook publishes a claim-triage skill that orchestrates the PolicyLookup and ClaimsData tools into a structured triage workflow:

```
Registry
├── MCP Records (tools — what to call)
│   ├── open-insurance-policy-lookup
│   └── open-insurance-claims-data
│
└── AGENT_SKILLS Records (workflows — how to reason)
    └── open-insurance-claim-triage
        "Given a claim ID, gather data from
         PolicyLookup + ClaimsData, assess
         severity, flag risks, produce report"
```

When Claude Code discovers a skill, it can extract the markdown instructions and install them as a local slash command (`.claude/commands/claim-triage.md`). The complete **Discover → Enable → Use** flow happens in a single session:

1. Search the Registry for skills related to claim triage
2. Claude Code extracts the `skillMd` content and writes it to `.claude/commands/claim-triage.md`
3. Invoke `/claim-triage CLM-2025-0067` — Claude follows the triage workflow, calling PolicyLookup and ClaimsData via the Gateway, and produces a structured severity report

## Cleanup

To avoid ongoing charges, delete the resources in reverse order. Each notebook includes a cleanup cell at the end, or you can run the steps manually:

1. Delete the Registry records, skill records, and the Registry itself (`03_registry_demo.ipynb` cleanup cell)
2. Delete the Cedar policies, policy engine, gateway targets, and the gateway (`01_agentcore_setup.ipynb` cleanup cell)
3. Run `terraform destroy` to remove the Lambda functions and IAM roles
4. Delete the Okta SPA application and demo users if no longer needed (`00_okta_setup.ipynb`)
5. Remove the MCP server configuration from Claude Code: `claude mcp remove agentcore-gateway`

## Conclusion

In this post, we walked through four notebooks that progressively build a centralized MCP server gateway using Amazon Bedrock AgentCore — from identity provider setup (`00_okta_setup.ipynb`), through infrastructure deployment and Cedar policy definition (`01_agentcore_setup.ipynb`), to connecting Claude Code with native OAuth (`02_claude_code_setup.ipynb`), and finally enabling tool discovery through the Registry (`03_registry_demo.ipynb`). This architecture applies wherever organizations need to give AI agents secure, governed access to enterprise tools.

Key takeaways:

- **Centralize access control at the gateway layer.** By moving authentication and authorization out of individual backends, you reduce code duplication and create a single point of policy enforcement. Backend services can focus on business logic with zero access control code.
- **Use Cedar policies for fine-grained tool access.** Cedar's principal-action-resource model maps naturally to the MCP tool discovery and invocation flow. You can control which users see which tools, and constrain tool inputs with `when` clauses for contextual authorization.
- **Connect AI coding assistants with native OAuth.** Claude Code's built-in MCP OAuth support enables browser-based PKCE authentication flows without custom token management. This demonstrates a pattern that can serve as a starting point for connecting AI agents to protected enterprise tools — additional security review, hardening, and testing are required before production use.
- **Discover tools through a managed Registry.** The AgentCore Registry provides a governed catalog where teams publish tools and agents discover them through natural language search — enabling a self-service "discover → install → use" flow without hardcoded tool lists.

Get started by exploring the following resources:

- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) product page
- [AgentCore Gateway documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [Cedar policy language reference](https://docs.cedarpolicy.com/)
- [Claude Code MCP documentation](https://docs.anthropic.com/en/docs/claude-code/mcp)



