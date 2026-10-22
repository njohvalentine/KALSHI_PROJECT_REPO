"""The eight conditions: which of the six controls are ON. B0 has none, P all, An is P with control n off."""

CONTROLS = {1: "Source classification", 2: "Least privilege", 3: "Deterministic tool gating", 4: "Schema validation", 5: "Dual-LLM isolation", 6: "Human approval"}
CONDITIONS: dict[str, frozenset[int]] = {"B0": frozenset(), "P": frozenset(CONTROLS), **{f"A{n}": frozenset(CONTROLS) - {n} for n in CONTROLS}}
