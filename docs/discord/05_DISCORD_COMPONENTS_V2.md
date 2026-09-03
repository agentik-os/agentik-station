# Discord Components V2 Strategy

Use the Discord Bot / Interactions API and Components V2 for new Station UI surfaces. The Discord Social SDK is not required for this bot cockpit architecture.

## Preferred primitives

- `Container` for a mission card;
- `Text Display` for complete readable text;
- `Section` for status + contextual accessory;
- `Separator` for hierarchy;
- `Button` for short actions;
- `Select Menu` for longer choice sets;
- `Modal` for structured input;
- `File` / `Media Gallery` for evidence or generated visual artifacts when appropriate.

A Components V2 message is created with the platform flag required by Discord. Once created in V2 mode it stays V2, so the Station renderer treats that message as a component tree for all later edits.

## No-truncation UX rule

Never solve long information by stuffing it into a button label.

```text
short action     -> Button
many choices     -> Select Menu
explanation      -> Text Display / Section
long form input  -> Modal
large output     -> File + summary
complex graph    -> Graph button + Agentik view / attached Mermaid
```

The renderer owns all platform limits and validates before send/edit. If a label or option cannot fit safely, it changes component type rather than silently cutting the semantic content.

## Accessibility and resilience

- all actions have text labels even when icons are used;
- destructive actions require clear wording and policy confirmation;
- disabled buttons indicate unavailable state;
- expired interactions return a fresh control surface rather than a dead end;
- message rendering must degrade to a clean legacy embed/text fallback if Components V2 is unavailable in a target environment.
