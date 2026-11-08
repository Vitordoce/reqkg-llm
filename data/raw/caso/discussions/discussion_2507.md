# Discussion #2507: Should FPrime be made CCSDS-compliant?

- Fonte: https://github.com/nasa/fprime/discussions/2507
- Autor (pseudonimizado): stakeholder-14

Right now, FPrime is configured to use it's own file transfer application, packetization protocol, and framing. FPrime does not follow the CCSDS standards for AOS Space Packets, the TM Transfer Frame architecture, the TC Transfer Frame protocol, nor the file transfer protocol laid out with the CFDP standards. This hampers FPrime-equipped missions from interacting with certain ground stations, utilize existing ground system tools, etc.

## Comentários

### Comentário 1 (stakeholder-06)

I support this sentiment! It would be an endeavor to change all of fprime to be CCSDS compliant, but I think aligning fprime with _some_ standard is better than having it use its own custom protocols

### Comentário 2 (stakeholder-08)

We also support the sentiment, but our dilemma is that we have supported multiple radio systems, many of which have their own protocol or hide CCSDS inside the hardware implementation. That's why we don't really want it to be inherent. Instead, we've provided a [Framer/Deframer](https://nasa.github.io/fprime/Design/communication-adapter-interface.html) pattern to implement other protocols. That would be a good place for CCSDS.

### Resposta 3 (stakeholder-15)

Internally, CCSDS has been successfully implemented in Fprime. While the [Framer/Deframer](https://nasa.github.io/fprime/Design/communication-adapter-interface.html) pattern facilitates protocol changes, we found it somewhat restrictive. To integrate CCSDS into Fprime, a fork of both Fprime and Fpp was necessary. I believe Fprime could benefit from slight modifications to streamline the integration of CCSDS packages.

The two key changes we've made (and would be willing to incorporate into Fprime) are:
1. Aligning all IDs (telemetry and events) within the same range, eliminating the need for an additional field to specify if a packet pertains to telemetry or an event.
2. Making IDs a parameter of the framer, allowing the protocol the freedom to determine how to serialize the ID.

Our architecture has not been published yet as we have submitted an abstract for the upcoming Flight Software Workshop. However, if you are interested, we can initiate a discussion before the workshop.

### Resposta 4 (stakeholder-16)

@stakeholder-08 "we have supported multiple radio systems, many of which have their own protocol or hide CCSDS inside the hardware implementation". 
Could you please tell more about radio systems that hide CCSDS inside the hardware implementation. Do you mean radio processors that automatically parse CCSDS packets?

### Resposta 5 (stakeholder-05)

We are hoping to implement CCSDS as multiple stages.  That way, if the radio implements Space Data Link Layer for example, you could still use SpacePacket in F Prime.

### Resposta 6 (stakeholder-16)

@stakeholder-05 does CCSDS implementation is planned to be part of the 3.5.0 release?
