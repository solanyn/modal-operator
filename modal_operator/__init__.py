"""Modal vGPU Operator - Kubernetes operator for serverless GPU workloads."""

__version__ = "0.1.0"


# Workaround for Modal library import bug (v1.1.4)
# The Modal library incorrectly imports from modal_operator.* instead of modal.*
# We create compatibility shim modules in this package that redirect to modal.*
