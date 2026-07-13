# CI-OS Admin Strategy

This fits the product vision because CI-OS cannot be a competitive intelligence operating system if operators cannot see and control the monitored universe. The target user is the operator/founder maintaining a CI tenant, not a public dashboard reader.

Trade-off: v1 is a safe local admin layer, not public multi-user SaaS administration. The key metric is whether adding or pausing a competitor/source changes the next Hermes sweep without touching YAML or Hermes core.

Defensibility comes from packaging the CI-OS business logic as a portable Hermes extension: the admin controls the CI registry while Hermes only schedules and runs the package.
