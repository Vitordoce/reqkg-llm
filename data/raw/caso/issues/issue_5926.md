# Issue #5926: Have TcDeframer dispatch based on VCID

- Fonte: https://github.com/nasa/fprime/issues/5926
- Autor (pseudonimizado): stakeholder-08
- Estado na coleta: closed

| | |
|:---|:---|
|**_F´ Version_**| 4.3 |
|**_Affected Component_**| Svc/Ccdsd/TcDeframer |
---
## Feature Description

Currently, the VCID is checked against a set value (or all):

https://github.com/nasa/fprime/blob/devel/Svc/Ccsds/TcDeframer/TcDeframer.cpp#L84

But then the VCID is discarded and not used.

Allow dispatching based on VCID to different uplink pipelines.

## Rationale

VCID is frequently used to direct uplink TC frames to different functions.

## Comentários

### Comentário 1 (stakeholder-02)

VCID should be set in the frameContext that's being passed around. If projects want to add custom routing based on that, they can slot in a router to do that from the updated frameContext.

### Comentário 2 (stakeholder-08)

Not sure I understand. Context gets passed in to TcDeframer:

https://github.com/nasa/fprime/blob/devel/Svc/Ccsds/TcDeframer/TcDeframer.cpp#L35

Are you suggesting that TcDeframer update the value of the context before passing it on?

### Comentário 3 (stakeholder-02)

Yes precisely - that's how other items get passed downstream. e.g. APID so that the router can do routing based on APID

https://github.com/nasa/fprime/blob/d7c76930bc7a32c742ef26241841f0a3b156480a/Svc/Ccsds/SpacePacketDeframer/SpacePacketDeframer.cpp#L102

The VCID doesn't contain any meaningful value before that (only what's configured to be default). I was saying "VCID should ..." as in we should add that. Currently isn't - will fix.

### Comentário 4 (stakeholder-08)

That's good for now, but it only works if the VCID encapsulates the same downstream format (e.g. SpacePacket), but if it isn't, then it breaks. IMHO, the best long-term approach would be to dispatch to different ports based on an VCID->port map.

### Comentário 5 (stakeholder-02)

With the updated frameContext you could slot in a VcidRouter between `TcDeframer --> VcidRouter --[fan out to multiple]--> {SpacePacketDeframer, OtherDeframers}` which would be the same functionality. I like the VCID->port map too.

### Comentário 6 (stakeholder-02)

Done in https://github.com/nasa/fprime/pull/5795 - feel free to reopen if need the port map functionality, but I contend this matches the SpacePacket APID routing pattern
