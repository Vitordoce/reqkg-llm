# Issue #5485: Multiplex Space Packets across TM/AOS for downlink efficiency

- Fonte: https://github.com/nasa/fprime/issues/5485
- Autor (pseudonimizado): stakeholder-08
- Estado na coleta: closed

| | |
|:---|:---|
|**_F´ Version_**|4.x |
|**_Affected Component_**| TM/AOS framer  |
---
## Feature Description

Have the TM framer completely fill TM frames with space packets, even if packets have to be multiplexed. Pre-pend each space packet with a standard CCSDS sync marker 0xEB90. Likewise, process uplink TCs assuming a sync marker.

## Rationale

Internal JPL projects assert that not completely filling TMs is a non-starter given link budgets.

## Comentários

### Comentário 1 (stakeholder-02)

For the packet filling, this is being implemented by https://github.com/nasa/fprime/pull/5631

The sync marker is another request and should be a separate ticket
