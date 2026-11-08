# Issue #5886: Svc/Ccsds/AosFramer,AosDeframer: M_PDU First Header Pointer special values are not CCSDS 732.0-B conformant

- Fonte: https://github.com/nasa/fprime/issues/5886
- Autor (pseudonimizado): stakeholder-07
- Estado na coleta: closed

| | |
|:---|:---|
|**_F´ Version_**| `devel` @ nasa/fprime b7dd5c4f8d26 |
|**_Affected Component_**| Svc/Ccsds/Types, Svc/Ccsds/AosFramer, Svc/Ccsds/AosDeframer |
|**_Severity_**| 4/5 |
---
## Problem Description

CCSDS 732.0-B §4.1.4.2 defines the M_PDU header as 5 reserved bits (`00000`) + an 11-bit First Header Pointer, with `0x7FF` = "no packet starts in this frame" and `0x7FE` = "idle data only". `Svc/Ccsds/Types/Types.fpp` defines `FHP_NO_PACKET_START = 0xFFFF` / `FHP_IDLE_DATA_ONLY = 0xFFFE`, `AosFramer.cpp:154` writes `0xFFFF` on the wire, and `AosDeframer` only recognizes those 16-bit values. Frames sent to or received from a conformant ground system are misparsed; the unit tests (`AosDeframerTestSupport.cpp:69`) only ever exchange the non-conformant values, so the gap is invisible.

## Context / Environment

Found by static AI full-codebase review of nasa/fprime `devel` at commit `b7dd5c4f8d268c5c70f0304a063d8ee27e026168` (current `devel` tip at posting time). Static finding; `fprime-util version-check` not applicable.

```
Finding id(s): dab3b78ab040, 34dec6b52b68, ab396b380c8d
```

## How to Reproduce

1. Frame a VC with no packet start; inspect the M_PDU header bytes: `FF FF` instead of `07 FF`.
2. Feed the deframer a conformant frame with FHP `0x07FF`; it is treated as a packet start at offset 2047.

## Expected Behavior

FHP special values `0x07FF`/`0x07FE`, reserved bits zero, on both framer and deframer; tests use the conformant values.

---
IAMAI

## Comentários

### Comentário 1 (stakeholder-13)

@stakeholder-07 Which version of the AOS standard are you using?
`CCSDS 732.0-B` doesn't actually spec a revision

### Comentário 2 (stakeholder-13)

I wrote to the B5 standard since that's the newest AFAIK version of the AOS Spec. Here are screenshots to show that it's actually a B4 vs B5 change. (and you really need to spec the version if you're gonna make a claim about the standard since they do make changes over time)

### Comentário 3 (stakeholder-13)

## B4
<img width="795" height="1153" alt="Image" src="https://github.com/user-attachments/assets/8b76a79a-fa30-455e-8fcb-42f3448db2f2" />

<img width="765" height="520" alt="Image" src="https://github.com/user-attachments/assets/4ea2030d-0625-4e57-9a59-88acece741f5" />
## B5 (my marked up copy)
note the "Issue 5" bars marking new/modified content

<img width="857" height="841" alt="Image" src="https://github.com/user-attachments/assets/ecbc1d5c-b99b-403f-a62c-af74d450c002" />

### Comentário 4 (stakeholder-13)

So the important take away is they un-reserved those bits in Issue 5

### Comentário 5 (stakeholder-13)

so, if desired, a bitmask down to the 11 bit version would produce the correct values for users who wanted to switch to the Issue 4 spec

### Comentário 6 (stakeholder-02)

Thanks @stakeholder-13 for looking into this. Do you want to take any action here (e.g. document?), or should we close this issue?

### Comentário 7 (stakeholder-13)

The UT listed literal values should get removed/fixed, but otherwise I'm consistent in my docs to call it a B-5 impl
