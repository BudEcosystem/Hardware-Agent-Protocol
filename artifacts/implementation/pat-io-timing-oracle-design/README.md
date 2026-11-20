# Finite I/O PAT timing and outcome design

This source-only handoff specifies whole-declared-domain timing checks and an
independent outcome reducer for the existing original GPIO/PWM simulator. It
continues the [earlier qualification design](references/00-DESIGN.md) after the
isolated fixed-unit compiler and trusted I/O resolver work.

The [design](DESIGN.md) distinguishes activation, completed cycle and established
idle state; includes early admission in lease calculations; and specifies the raw
evidence needed to check those claims. Its deterministic clock profile is a
simulation policy, not a real-time guarantee for a host or microcontroller.

[Inputs](inputs.json) pin 19 selected project files and seven historical reference
documents. [Source notes](SOURCE-NOTES.md) identify the inspected implementation
seams. The [index](index.json) seals this handoff. Preparation verified bytes with
standard-library tools; it imported no project code, constructed no Runtime and
ran no project tests, qualification worker, model or hardware. The timing policy,
worker and reducer specified here remain unimplemented.

The primary agent completed this design after the helper agents encountered an
account usage limit. There is no independent final review of this handoff.
