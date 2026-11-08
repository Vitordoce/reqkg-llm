# Issue #5574: CfdpManager: support files larger than 4 GiB

- Fonte: https://github.com/nasa/fprime/issues/5574
- Autor (pseudonimizado): stakeholder-09
- Estado na coleta: open

## Summary

`Svc::Ccsds::Cfdp::FileSize` (defined in `default/config/CfdpCfg.fpp`) is configurable to `U64` and the CFDP protocol permits 64-bit file sizes and offsets. The PDU serialization layer is already width-agnostic (it keys off `sizeof(FileSize)` and the large-file flag), so `type FileSize = U64` produces spec-compliant 64-bit PDUs on the wire.

However, several call sites above the PDU layer still narrow file size/offset back to `U32`. As a result the component is only validated for the `U32` value range, and transfers larger than 4 GiB would truncate these narrowed values.

Discovered during PR review: https://github.com/nasa/fprime/pull/5138#discussion_r3661025986

## Known narrowing sites

- `Svc/Ccsds/CfdpManager/Types/FileDataPdu.cpp` (32-bit offset branch): `U32 offset32 = static_cast<U32>(this->m_offset);`
- `Svc/Ccsds/CfdpManager/Engine.cpp`: `static_cast<U32>(txn->m_fsize)` when populating telemetry/events
- `Svc/Ccsds/CfdpManager/TransactionTx.cpp`: `static_cast<U32>(this->m_fsize)`
- `Svc/Ccsds/CfdpManager/TransactionRx.cpp`: `static_cast<U32>(...)` on offset/size for CRC and gap computation

Telemetry/event channels reporting file size/offset should also be reviewed for U64 width.

## Acceptance criteria

- Audit and remove or widen `FileSize` -> `U32` narrowing on the transfer path
- Add UT coverage exercising a `FileSize = U64` build with offsets beyond the 32-bit range
- Update the `FileSize` doc comment in `CfdpCfg.fpp` once U64 is validated end to end
