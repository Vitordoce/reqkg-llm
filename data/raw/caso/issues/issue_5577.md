# Issue #5577: CfdpManager: support running the sched call at a rate other than 1 Hz

- Fonte: https://github.com/nasa/fprime/issues/5577
- Autor (pseudonimizado): stakeholder-09
- Estado na coleta: open

## Summary

`CfdpManager` drives its CFDP engine timers from the `run1Hz` scheduler input port, and the timer logic assumes exactly one invocation per second. There is no configuration to run the sched call at a different rate. A configuration constant should decouple the sched tick rate from the timer semantics so the component can be driven at rates other than 1 Hz.

## Current 1 Hz assumption

- `run1Hz` port, documented "must be invoked at 1 Hz in order to satisfy CFDP timer logic": `Svc/Ccsds/CfdpManager/CfdpManager.fpp:22-23`
- Handler calls `m_engine->cycle()` once per invocation and emits telemetry "once per second": `Svc/Ccsds/CfdpManager/CfdpManager.cpp:79`
- Core assumption lives in the `Timer` class: `Timer::run()` decrements `secondsRemaining` by exactly 1 per call and expires at 0 (1 tick == 1 second, hardcoded): `Svc/Ccsds/CfdpManager/Timer.cpp:41-50` (`Timer.hpp:40,49,61`)
- Timers driven per tick:
  - TX ack timer: `Svc/Ccsds/CfdpManager/TransactionTx.cpp:143`
  - TX inactivity timer: `Svc/Ccsds/CfdpManager/TransactionTx.cpp:190`
  - RX ack timer: `Svc/Ccsds/CfdpManager/TransactionRx.cpp:205`
  - Poll-directory interval timer: `Svc/Ccsds/CfdpManager/Channel.cpp:378`
- Timeout values are all expressed in seconds: `ack_timer`, `inactivity_timer` in `Svc/Ccsds/CfdpManager/Types/Types.fpp:74-75` (defaults in `Parameters.fppi:44-45`)
- There is no existing rate/frequency configuration constant in `default/config/CfdpCfg.fpp`.

## Acceptance criteria

- Add a tick-rate configuration constant (e.g. `SchedTicksPerSecond`) to `default/config/CfdpCfg.fpp`
- Have the timer logic (`Timer::run()`/`setTimer()` or the engine cycle) honor it so N sched ticks == 1 second
- Update the `run1Hz` port name and documentation to reflect the configurable rate
- Add UT coverage exercising a non-1 Hz tick rate
