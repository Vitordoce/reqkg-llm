# Issue #5835: Add Replay-Attack Prevention to AESGsmEncryptor/Decryptor

- Fonte: https://github.com/nasa/fprime/issues/5835
- Autor (pseudonimizado): stakeholder-05
- Estado na coleta: open

| | |
|:---|:---|
|**_F´ Version_**| |
|**_Affected Component_**|  |
---
## Feature Description

This can be done by setting the IV as a sequence counter instead of random values.

## Comentários

### Comentário 1 (stakeholder-02)

This needs to be an agreement between ground and flight as to how they allow IV to be set - we should look into whether the SDLS standard says anything about it. In the prototype a few years ago we had a monotonically increasing counter half of the IV, and a random half. The decryptor would validate that the counter half would match. But I'm not sure how it would handle packet drops.

### Comentário 2 (stakeholder-12)

I checked CCSDS 355.0-B-2 on this. The standard already defines how to tolerate gaps: the receiver maintains an anti-replay sequence number plus a Sequence Number Window, and frames outside that window are discarded. The window is explicitly intended to account for transmission gaps/delays.

For authenticated encryption with a simple incrementing IV, the IV itself may serve as the anti-replay sequence number, so a separate sequence-number field is not required. That seems like the cleanest fit here: per-SA monotonic IV/sequence state on transmit, plus per-SA receive state/window rather than exact-next-value matching.

I would hold off on implementation until we agree the SA/window representation and rollover/persistence behavior, but this should resolve the packet-drop question from the standard.
