"""The indirect prompt injection experiment (docs/specs/FEAT-20261022-0946-injection-experiment.md).

Poisoned pages are run through the real research, judge and forecaster steps of Our Agent, with one security control at a time switched
off *in this harness only*. The unsafe variants never exist in the app. All pages and hosts are fictional and local; nothing is ordered."""
