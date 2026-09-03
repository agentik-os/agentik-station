# Changelog v9 — Orchestration Intelligence

Station v9 adds a canonical orchestration/evidence layer over Hermes without replacing Hermes runtime primitives.

## Added

- seven capability lanes: Clarify/Plan, Build with Leverage, Research/Learn, Code/Ship Safely, Polished Deliverables, Remember/Operate, Connect with Clear Boundaries;
- Evidence Before Claims state model;
- prepared vs observed vs reported vs verified vs read-back vs accepted semantics;
- explicit durable owner and verification owner per mission graph node;
- connector/capability readiness probing before plan dependency;
- executor-neutral coding/dispatch language;
- parallel fan-out/fan-in ownership and isolation rules;
- artifact taste + render-quality gates;
- review-first memory and operational readiness / next-repair contract;
- optional Oh My Hermes interoperability contract;
- Discord evidence-status projection;
- new JSON schemas, policy examples and deterministic evidence-state helper;
- OS Contract v2 extension requiring orchestration + claim/evidence policy.

## Non-goals

- OMH is not a mandatory dependency;
- Station does not duplicate Hermes runtime;
- a plan/task checkbox does not become evidence;
- an executor completion message does not become verification.
