# Issue #5579: CfdpManager: add TLV support for Metadata PDU options and Finished PDU filestore responses

- Fonte: https://github.com/nasa/fprime/issues/5579
- Autor (pseudonimizado): stakeholder-09
- Estado na coleta: open

## Summary

`CfdpManager` has generic TLV (Type-Length-Value) infrastructure but does not fully support TLVs where the CFDP spec allows them. Two gaps should be addressed:

1. **Metadata PDU optional parameters** (misc metadata, user messages, filestore requests, etc.) encoded as TLVs are not supported at all.
2. **Finished PDU TLVs** paired to requests received in Metadata PDUs (e.g. filestore responses) are not generated or paired.

## Current state

**TLV infrastructure exists but is mostly opaque:**
- `TlvType` enum defines all 6 CCSDS §5.4 table 5-3 type codes: `Svc/Ccsds/CfdpManager/Types/Tlv.hpp:21-28`. Only `TLV_TYPE_ENTITY_ID` gets structured encode/decode; all other types round-trip as opaque raw bytes (`Tlv.cpp`).
- `MaxTlv = 4`: `default/config/CfdpCfg.fpp:88`

**Metadata PDU: no TLV/options support (part 1):**
- `MetadataPdu` has no `TlvList` member and does not include `Tlv.hpp` (`MetadataPdu.hpp:20-96`).
- `toSerialBuffer` emits no options field, and `fromSerialBuffer` returns after the two filename LVs without consuming any trailing options; TLVs are silently dropped: `Svc/Ccsds/CfdpManager/Types/MetadataPdu.cpp:168-247`.

**FIN PDU: wire encode/decode works, but only Entity-ID-on-error is used (part 2):**
- FIN encodes/decodes a `TlvList`: `Svc/Ccsds/CfdpManager/Types/FinPdu.cpp:117` (serialize) and `:151` (deserialize).
- Only an Entity ID TLV is emitted, and only on error: `Svc/Ccsds/CfdpManager/Engine.cpp:317-322`.
- Received non-EntityID TLVs are ignored: `Svc/Ccsds/CfdpManager/Engine.cpp:452-458`.
- No filestore-response generation and no pairing of FIN TLVs to Metadata filestore requests.
- "Future enhancement" comments at `Engine.cpp:438-441` and `:455-458`.

## Acceptance criteria

- Add a TLV/options field to `MetadataPdu` with serialize and parse support
- Parse message-to-user / filestore-request TLVs on receive
- Generate filestore-response TLVs in the FIN PDU, paired to the filestore requests received in the Metadata PDU
- Add UT coverage for Metadata TLV round-trip and FIN filestore-response pairing

## Reference

CCSDS 727.0-B-5, section 5.4, table 5-3
