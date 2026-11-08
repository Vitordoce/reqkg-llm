# Issue #5583: CfdpManager: harden receive path (sandbox file paths, zero-size files, offset validation) — follow-up to #5138

- Fonte: https://github.com/nasa/fprime/issues/5583
- Autor (pseudonimizado): stakeholder-07
- Estado na coleta: closed

Follow-up to #5138 (CCSDS File Delivery Protocol - CfdpManager). Review of that PR identified four issues in the `Svc/Ccsds/CfdpManager` receive path that are reachable from remote (uplink) PDU content, i.e. from untrusted input. They are captured here so #5138 can land and these can be addressed as a focused follow-up.

## 1. Uplinked file paths are not sandboxed (path traversal / arbitrary file write)

`Transaction` holds a raw `Os::File`:

- `Svc/Ccsds/CfdpManager/Transaction.hpp:770` — `Os::File m_fd;`
- `Svc/Ccsds/CfdpManager/TransactionRx.cpp:366` — opens `m_history->fnames.dst_filename` (taken verbatim from the received Metadata PDU) with `OPEN_CREATE`.

`MetadataPdu::fromSerialBuffer` validates only the filename *length* against `MaxFilePathSize`, not its content, so a relative path such as `../../...` is accepted and written wherever the process can reach.

The components CfdpManager is intended to replace both use `Os::SandboxedFile`:

- `Svc/FileUplink/FileUplink.hpp:46`
- `Svc/FileDownlink/FileDownlink.hpp:86`

and `Os/SandboxedFile.hpp` names "CFDP receivers" explicitly as a motivating case. As written this is a security regression relative to FileUplink.

**Proposed fix:** use `Os::SandboxedFile` for the CFDP RX write path (and consider it for the TX read path and directory playback), configured at deployment startup.

## 2. Zero-byte file transfer trips an assert

`Svc/Ccsds/CfdpManager/Chunk.cpp:105` — `FW_ASSERT(total); /* does it make sense to have a 0 byte file? */`

`total` is `m_fsize`, assigned unvalidated from the remote Metadata PDU (`Engine.cpp:402`) and consumed via `r2Complete` (`TransactionRx.cpp:436`). A zero-length file is legal CFDP. The transmit side rejects size 0 locally (`TransactionTx.cpp:530`) but the receive side does not, so a peer CFDP implementation sending an empty file asserts the FSW.

**Proposed fix:** handle `m_fsize == 0` as a valid, immediately-complete reception (or reject it with a fault/EVR) before any `computeGaps()` call.

## 3. Unvalidated FileData offset can overflow and trip an assert

`Svc/Ccsds/CfdpManager/Chunk.cpp:70` — `FW_ASSERT((offset + size) >= offset, ...)`

`r2SubstateRecvFileData` calls `chunks.add(fd.getOffset(), fd.getDataSize())` at `TransactionRx.cpp:776`, while the bounds check in `rProcessFd` (`TransactionRx.cpp:511`) is gated on `m_flags.rx.md_recv`. Class 2 deliberately enters R2 on FileData received before Metadata, so a single FileData PDU with an offset near 2^32 overflows the `FileSize` (U32) addition and asserts. The same path also seeks and writes at that offset first, producing a ~4 GB sparse file.

**Proposed fix:** validate the offset/length of every FileData PDU (overflow-safe, subtraction form) regardless of `md_recv`, and reject out-of-range PDUs with an EVR/fault counter rather than an assert.

## 4. Deserialization status discarded in `FileDataPdu::fromSerialBuffer`

`Svc/Ccsds/CfdpManager/Types/FileDataPdu.cpp:137` — the return of `serialBuffer.deserializeTo(this->m_offset)` is not checked, so a truncated PDU leaves a stale/garbage offset that is then used for the subsequent `seek()` and `write()`.

**Proposed fix:** check the status and return it on failure.

## Notes

- Findings 1-3 are considered must-fix; 4 is a small correctness fix in the same area.
- Related lower-severity observation (not required for this ticket): `FileInRequest`, which contains two polymorphic `Fw::String` members, is passed through `Os::Queue` via `reinterpret_cast<U8*>` at `Svc/Ccsds/CfdpManager/CfdpManager.cpp:233`. This is a byte copy of a non-trivially-copyable type: it works within a single process but is formally undefined behavior.

## Comentários

### Comentário 1 (stakeholder-07)

Findings 2–4 were addressed in #5585 (merged 2026-08-10). Finding 1 (path sandboxing) is tracked separately in #5510. Recommend closing this issue in favor of #5510.

[Written by Devin](https://nasa-jpl-demo.devinenterprise.com/sessions/83546cf842f144298a0b6a302e0cb6d4)
