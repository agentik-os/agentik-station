# Reviewed server software bundles

These manifests install actual immutable Linux AMD64 server images and required
infrastructure in the local Podman store. They do not start services, create
accounts, expose ports, migrate databases or enroll Hermes profiles.

| Bundle | Images | Deployment/acceptance requirements |
| --- | ---: | --- |
| [Langfuse](langfuse.json) | 6 | [Observability service guide](langfuse/README.md) |
| [Honcho](honcho.json) | 3 | [Memory service guide](honcho/README.md) |
| [Hindsight](hindsight.json) | 2 | [Memory service guide](hindsight/README.md) |
| [ChatbotX](chatbotx.json) | 9 | [Application and MCP service guide](chatbotx/README.md) |

```bash
station deps service-plan --component langfuse
sudo station deps install --component langfuse
sudo station deps service-check --component langfuse
```

Use the immutable installed Station release, not an operator-writable checkout.
Successful image checks establish `SOFTWARE_INSTALLED`, with
`configuration_required: true` and `operational: false`. The full requirement
inventory and remaining security gate are documented in
[FULL_STACK.md](../../docs/dependencies/FULL_STACK.md).
