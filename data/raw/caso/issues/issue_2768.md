# Issue #2768: Implement CCSDS File Delivery Protocol

- Fonte: https://github.com/nasa/fprime/issues/2768
- Autor (pseudonimizado): stakeholder-01
- Estado na coleta: closed

| | |
|:---|:---|
|**_F´ Version_**| |
|**_Affected Component_**|  |
---
## Feature Description

This feature introduces to F' the core file delivery capabilities from the latest CCSDS File Delivery Protocol (CFDP).

The goal is to implement CFDP in several stages. The recommend standard describes two service classes: Class 1 CFDP (unreliable transfer) and Class 2 CFDP (reliable transfer). The following subtasks only implement CFDP features required for core file delivery. Filestore requests, user operations, and other optional convenience features are not currently within the goals of this feature.

Recommended Standard:
https://public.ccsds.org/Pubs/727x0b5.pdf

Informational Reports:
https://public.ccsds.org/Pubs/720x1g4.pdf
https://public.ccsds.org/Pubs/720x2g4.pdf

For each subtask there is a corresponding task for implementing the change on the GDS side.

### Subtasks
- [ ] #2769 
- [ ] #2771 
- [ ] #2798 
- [ ] GDS - Implement core Class 1 CFDP procedures without transaction closure
- [ ] Implement transaction closure option
- [ ] GDS - Implement transaction closure option
- [ ] Refactor CFDP with CFDP checksum and CRC algorithms
- [ ] GDS - Refactor CFDP with CFDP checksum and CRC algorithms
- [ ] Create CFDP Class 2 file packets
- [ ] GDS - Create CFDP Class 2 file packets
- [ ] Implement core Class 2 CFDP procedures
- [ ] GDS - Implement core Class 2 CFDP procedures

## Rationale

This feature moves F' towards CCSDS compliance, allowing interoperability with other CCSDS compliant systems. By itself, Class 1 CFDP provides a base file transfer capability. Class 2 CFDP provides reliable file transfer over unreliable connections and simplifies operations through automated retransmission.

## Comentários

### Comentário 1 (stakeholder-02)

Preliminary work is located here: https://github.com/thomas-bc/fprime/tree/issue-2769

### Comentário 2 (stakeholder-03)

Proposed initial design for implementing the core Class 2 CFDP protocol in F Prime:
[cfdp-class2.txt](https://github.com/user-attachments/files/18383708/cfdp-class2.txt)

Here's an explanation of the key aspects:
1. Core CFDP Class 2 Features
- File transmission with acknowledgment and retransmission
- Modular file checksum calculation (as specified in section 4.2.5)  
- Support for segmented file data PDUs with offset tracking
- PDU acknowledgment and negative acknowledgment handling
- Transaction state and retransmission buffer management

2. Key Design Elements
- CfdpClass2Sender: Primary component implementing the sending side of Class 2 CFDP
- TransactionState: Tracks ongoing transaction details including file info and progress
- RetransmitBuffer: Stores PDUs for potential retransmission 
- Follows F' component patterns and integrates with F' ports and timing

The implementation sketch provides the core framework needed for reliable file transfer per the CFDP spec. Here are the next recommended steps:
1. Review and refine the core Class 2 implementation design
2. Complete the implementation including integration with F' ports/timing
3. Implement matching receiver-side component
4. Add transaction closure per section 4.6.3.2.2
5. Integrate updated checksum logic per section 4.2
6. Add optional Keep Alive for progress monitoring

### Comentário 3 (stakeholder-04)

Is this still planned?

### Comentário 4 (stakeholder-05)

Yes it is still planned.  It is currently being worked by one of our customers, and we have hopes we can make it opensource when finished.

### Comentário 5 (stakeholder-06)

Any updates on the status of this ticket? Is it still being worked on?

### Comentário 6 (stakeholder-05)

Same as above.  It is being worked.

### Comentário 7 (stakeholder-02)

PR open!! https://github.com/nasa/fprime/pull/5138
